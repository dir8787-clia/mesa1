"""LocalNet Messenger - WebSocket Handler and Message Processing"""
import asyncio
import json
import time
import uuid
import hashlib
import secrets
from pathlib import Path
from typing import Optional, Dict, Any, Set
import logging

import argon2

from shared.protocol import MessageType, ProtocolMessage, create_message
from server.database import Database

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages active WebSocket connections"""
    
    def __init__(self):
        self.connections: Dict[str, Any] = {}  # user_id -> websocket
        self.user_ids: Dict[Any, str] = {}  # websocket -> user_id
    
    def add_connection(self, ws, user_id: str):
        """Add a connection"""
        self.connections[user_id] = ws
        self.user_ids[ws] = user_id
    
    def remove_connection(self, ws):
        """Remove a connection"""
        user_id = self.user_ids.pop(ws, None)
        if user_id:
            self.connections.pop(user_id, None)
    
    def get_user_id(self, ws) -> Optional[str]:
        """Get user ID for a connection"""
        return self.user_ids.get(ws)
    
    async def send_to_user(self, user_id: str, message: ProtocolMessage):
        """Send message to a specific user"""
        ws = self.connections.get(user_id)
        if ws:
            try:
                await ws.send_str(message.to_json())
            except Exception as e:
                logger.error(f"Error sending to {user_id}: {e}")
    
    async def broadcast(self, message: ProtocolMessage, exclude_user: str = None):
        """Broadcast message to all connected users"""
        for user_id, ws in list(self.connections.items()):
            if user_id != exclude_user:
                try:
                    await ws.send_str(message.to_json())
                except Exception as e:
                    logger.error(f"Error broadcasting to {user_id}: {e}")
    
    async def send_to_chat(self, chat_members: Set[str], message: ProtocolMessage,
                          exclude_user: str = None):
        """Send message to all members of a chat"""
        for user_id in chat_members:
            if user_id != exclude_user:
                await self.send_to_user(user_id, message)


class MessageHandler:
    """Handles incoming protocol messages"""
    
    def __init__(self, db: Database, conn_manager: ConnectionManager):
        self.db = db
        self.conn_manager = conn_manager
        self.ph = argon2.PasswordHasher()
        
        # Message type handlers
        self.handlers = {
            'auth.register': self.handle_register,
            'auth.login': self.handle_login,
            'auth.logout': self.handle_logout,
            'message.send': self.handle_message_send,
            'message.edit': self.handle_message_edit,
            'message.delete': self.handle_message_delete,
            'message.read': self.handle_message_read,
            'message.history': self.handle_message_history,
            'chat.create': self.handle_chat_create,
            'chat.list': self.handle_chat_list,
            'typing.start': self.handle_typing,
            'typing.stop': self.handle_typing,
            'heartbeat': self.handle_heartbeat,
            'user.list': self.handle_user_list,
        }
    
    async def handle_message(self, ws, data: str):
        """Process incoming message"""
        try:
            msg = ProtocolMessage.from_json(data)
            logger.debug(f"Received: {msg.type} from {msg.sender}")
            
            handler = self.handlers.get(msg.type)
            if handler:
                response = await handler(ws, msg)
                if response:
                    await ws.send_str(response.to_json())
            else:
                logger.warning(f"Unknown message type: {msg.type}")
                error_msg = self.create_message(
                    MessageType.ERROR,
                    {'error': f'Unknown message type: {msg.type}'},
                    sender='server'
                )
                await ws.send_str(error_msg.to_json())
                
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON: {e}")
        except Exception as e:
            logger.error(f"Error handling message: {e}", exc_info=True)
            error_msg = self.create_message(
                MessageType.ERROR,
                {'error': str(e)},
                sender='server'
            )
            await ws.send_str(error_msg.to_json())
    
    def create_message(self, msg_type: MessageType, payload: Dict[str, Any],
                      sender: str = 'server') -> ProtocolMessage:
        """Create a protocol message"""
        return create_message(msg_type, payload, sender=sender)
    
    async def handle_register(self, ws, msg: ProtocolMessage) -> Optional[ProtocolMessage]:
        """Handle user registration"""
        username = msg.payload.get('username', '').strip()
        password = msg.payload.get('password', '')
        display_name = msg.payload.get('display_name', username)
        
        if len(username) < 3:
            return self.create_message(
                MessageType.AUTH_REGISTER,
                {'success': False, 'error': 'Username must be at least 3 characters'}
            )
        
        if len(password) < 6:
            return self.create_message(
                MessageType.AUTH_REGISTER,
                {'success': False, 'error': 'Password must be at least 6 characters'}
            )
        
        # Check if user exists
        existing = await self.db.get_user_by_username(username)
        if existing:
            return self.create_message(
                MessageType.AUTH_REGISTER,
                {'success': False, 'error': 'Username already exists'}
            )
        
        # Hash password
        password_hash = self.ph.hash(password)
        
        # Create user
        user_id = str(uuid.uuid4())
        success = await self.db.create_user(user_id, username, password_hash, display_name)
        
        if success:
            logger.info(f"User registered: {username} ({user_id})")
            return self.create_message(
                MessageType.AUTH_REGISTER,
                {'success': True, 'user_id': user_id, 'username': username}
            )
        else:
            return self.create_message(
                MessageType.AUTH_REGISTER,
                {'success': False, 'error': 'Failed to create user'}
            )
    
    async def handle_login(self, ws, msg: ProtocolMessage) -> Optional[ProtocolMessage]:
        """Handle user login"""
        username = msg.payload.get('username', '').strip()
        password = msg.payload.get('password', '')
        device_id = msg.payload.get('device_id', 'unknown')
        device_name = msg.payload.get('device_name', 'Unknown Device')
        
        user = await self.db.get_user_by_username(username)
        if not user:
            return self.create_message(
                MessageType.AUTH_LOGIN,
                {'success': False, 'error': 'Invalid credentials'}
            )
        
        # Verify password
        try:
            self.ph.verify(user['password_hash'], password)
        except argon2.exceptions.VerifyMismatchError:
            return self.create_message(
                MessageType.AUTH_LOGIN,
                {'success': False, 'error': 'Invalid credentials'}
            )
        
        # Create session token
        token = secrets.token_urlsafe(32)
        session_id = str(uuid.uuid4())
        expires_at = time.time() + (30 * 24 * 60 * 60)  # 30 days
        
        await self.db.create_session(session_id, user['id'], device_id, device_name, token, expires_at)
        
        # Update user status
        await self.db.update_user_status(user['id'], 'online')
        
        # Store connection
        self.conn_manager.add_connection(ws, user['id'])
        
        logger.info(f"User logged in: {username} ({user['id']})")
        
        return self.create_message(
            MessageType.AUTH_LOGIN,
            {
                'success': True,
                'user_id': user['id'],
                'username': user['username'],
                'display_name': user['display_name'],
                'token': token
            }
        )
    
    async def handle_logout(self, ws, msg: ProtocolMessage):
        """Handle user logout"""
        user_id = self.conn_manager.get_user_id(ws)
        if user_id:
            token = msg.token
            await self.db.delete_session(token)
            await self.db.update_user_status(user_id, 'offline')
            self.conn_manager.remove_connection(ws)
            logger.info(f"User logged out: {user_id}")
    
    async def handle_message_send(self, ws, msg: ProtocolMessage):
        """Handle sending a message"""
        user_id = self.conn_manager.get_user_id(ws)
        if not user_id:
            return self.create_message(MessageType.MESSAGE_SEND, {'success': False, 'error': 'Not authenticated'})
        
        chat_id = msg.payload.get('chat_id')
        content = msg.payload.get('content', '')
        content_type = msg.payload.get('content_type', 'text')
        reply_to = msg.payload.get('reply_to')
        
        if not chat_id or not content:
            return self.create_message(MessageType.MESSAGE_SEND, {'success': False, 'error': 'Invalid message'})
        
        # Verify user is in chat
        members = await self.db.get_chat_members(chat_id)
        member_ids = {m['id'] for m in members}
        if user_id not in member_ids:
            return self.create_message(MessageType.MESSAGE_SEND, {'success': False, 'error': 'Not in chat'})
        
        # Save message
        msg_id = str(uuid.uuid4())
        await self.db.create_message(msg_id, chat_id, user_id, content, content_type, reply_to)
        
        # Broadcast to chat members
        message_data = {
            'message_id': msg_id,
            'chat_id': chat_id,
            'sender_id': user_id,
            'content': content,
            'content_type': content_type,
            'reply_to': reply_to,
            'timestamp': time.time()
        }
        
        broadcast_msg = self.create_message(MessageType.MESSAGE_SEND, message_data, sender=user_id)
        await self.conn_manager.send_to_chat(member_ids, broadcast_msg)
        
        return self.create_message(MessageType.MESSAGE_SEND, {'success': True, 'message_id': msg_id})
    
    async def handle_message_edit(self, ws, msg: ProtocolMessage):
        """Handle editing a message"""
        user_id = self.conn_manager.get_user_id(ws)
        if not user_id:
            return self.create_message(MessageType.MESSAGE_EDIT, {'success': False, 'error': 'Not authenticated'})
        
        msg_id = msg.payload.get('message_id')
        content = msg.payload.get('content', '')
        
        if not msg_id or not content:
            return self.create_message(MessageType.MESSAGE_EDIT, {'success': False, 'error': 'Invalid request'})
        
        success = await self.db.edit_message(msg_id, content, user_id)
        
        if success:
            # Broadcast edit
            edit_msg = self.create_message(
                MessageType.MESSAGE_EDIT,
                {'message_id': msg_id, 'content': content, 'edited_at': time.time()},
                sender=user_id
            )
            # Get chat info to broadcast
            # For simplicity, we'd need to look up the chat
            await self.conn_manager.broadcast(edit_msg)
            
        return self.create_message(MessageType.MESSAGE_EDIT, {'success': success})
    
    async def handle_message_delete(self, ws, msg: ProtocolMessage):
        """Handle deleting a message"""
        user_id = self.conn_manager.get_user_id(ws)
        if not user_id:
            return self.create_message(MessageType.MESSAGE_DELETE, {'success': False, 'error': 'Not authenticated'})
        
        msg_id = msg.payload.get('message_id')
        if not msg_id:
            return self.create_message(MessageType.MESSAGE_DELETE, {'success': False, 'error': 'Invalid request'})
        
        success = await self.db.delete_message(msg_id, user_id)
        
        if success:
            delete_msg = self.create_message(
                MessageType.MESSAGE_DELETE,
                {'message_id': msg_id},
                sender=user_id
            )
            await self.conn_manager.broadcast(delete_msg)
        
        return self.create_message(MessageType.MESSAGE_DELETE, {'success': success})
    
    async def handle_message_read(self, ws, msg: ProtocolMessage):
        """Handle marking messages as read"""
        user_id = self.conn_manager.get_user_id(ws)
        if not user_id:
            return self.create_message(MessageType.MESSAGE_READ, {'success': False, 'error': 'Not authenticated'})
        
        msg_id = msg.payload.get('message_id')
        if msg_id:
            await self.db.mark_message_read(msg_id, user_id)
        
        return self.create_message(MessageType.MESSAGE_READ, {'success': True})
    
    async def handle_message_history(self, ws, msg: ProtocolMessage):
        """Handle getting message history"""
        user_id = self.conn_manager.get_user_id(ws)
        if not user_id:
            return self.create_message(MessageType.MESSAGE_HISTORY, {'success': False, 'error': 'Not authenticated'})
        
        chat_id = msg.payload.get('chat_id')
        limit = msg.payload.get('limit', 50)
        before = msg.payload.get('before')
        
        if not chat_id:
            return self.create_message(MessageType.MESSAGE_HISTORY, {'success': False, 'error': 'Invalid request'})
        
        # Verify access
        members = await self.db.get_chat_members(chat_id)
        member_ids = {m['id'] for m in members}
        if user_id not in member_ids:
            return self.create_message(MessageType.MESSAGE_HISTORY, {'success': False, 'error': 'Access denied'})
        
        messages = await self.db.get_message_history(chat_id, limit, before)
        
        return self.create_message(
            MessageType.MESSAGE_HISTORY,
            {'success': True, 'messages': messages, 'chat_id': chat_id}
        )
    
    async def handle_chat_create(self, ws, msg: ProtocolMessage):
        """Handle creating a new chat"""
        user_id = self.conn_manager.get_user_id(ws)
        if not user_id:
            return self.create_message(MessageType.CHAT_CREATE, {'success': False, 'error': 'Not authenticated'})
        
        chat_type = msg.payload.get('type', 'private')
        name = msg.payload.get('name')
        members = msg.payload.get('members', [user_id])
        
        chat_id = str(uuid.uuid4())
        await self.db.create_chat(chat_id, chat_type, name, user_id)
        
        # Add members
        for member_id in members:
            role = 'owner' if member_id == user_id else 'member'
            await self.db.add_chat_member(chat_id, member_id, role)
        
        # Notify members
        chat_info = {
            'chat_id': chat_id,
            'type': chat_type,
            'name': name,
            'members': members,
            'created_by': user_id
        }
        
        notify_msg = self.create_message(MessageType.CHAT_CREATE, chat_info, sender=user_id)
        for member_id in members:
            await self.conn_manager.send_to_user(member_id, notify_msg)
        
        return self.create_message(MessageType.CHAT_CREATE, {'success': True, 'chat_id': chat_id})
    
    async def handle_chat_list(self, ws, msg: ProtocolMessage):
        """Handle getting user's chat list"""
        user_id = self.conn_manager.get_user_id(ws)
        if not user_id:
            return self.create_message(MessageType.CHAT_LIST, {'success': False, 'error': 'Not authenticated'})
        
        chats = await self.db.get_user_chats(user_id)
        
        return self.create_message(
            MessageType.CHAT_LIST,
            {'success': True, 'chats': chats}
        )
    
    async def handle_typing(self, ws, msg: ProtocolMessage):
        """Handle typing indicator"""
        user_id = self.conn_manager.get_user_id(ws)
        if not user_id:
            return
        
        chat_id = msg.payload.get('chat_id')
        if not chat_id:
            return
        
        # Get chat members
        members = await self.db.get_chat_members(chat_id)
        member_ids = {m['id'] for m in members}
        
        typing_msg = self.create_message(
            msg.type,
            {'chat_id': chat_id, 'user_id': user_id},
            sender=user_id
        )
        
        # Send to other members
        for member_id in member_ids:
            if member_id != user_id:
                await self.conn_manager.send_to_user(member_id, typing_msg)
    
    async def handle_heartbeat(self, ws, msg: ProtocolMessage):
        """Handle heartbeat"""
        return self.create_message(
            MessageType.HEARTBEAT,
            {'timestamp': time.time(), 'status': 'ok'}
        )
    
    async def handle_user_list(self, ws, msg: ProtocolMessage):
        """Handle getting user list"""
        user_id = self.conn_manager.get_user_id(ws)
        if not user_id:
            return self.create_message(MessageType.USER_LIST, {'success': False, 'error': 'Not authenticated'})
        
        users = await self.db.get_all_users()
        
        # Add online status from connections
        for user in users:
            user['online'] = user['id'] in self.conn_manager.connections
        
        return self.create_message(
            MessageType.USER_LIST,
            {'success': True, 'users': users}
        )
