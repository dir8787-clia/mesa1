"""
LocalNet Messenger Server - WebSocket Handlers
Handles all client connections and message routing
"""
import asyncio
import json
import time
import uuid
import os
from pathlib import Path
from typing import Dict, Set, Optional, Any
from collections import defaultdict
import aiofiles
from argon2 import PasswordHasher
from cryptography.fernet import Fernet

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.protocol import MessageType, ProtocolMessage, create_message
from server.database import Database


class ConnectionManager:
    """Manages active WebSocket connections"""
    
    def __init__(self):
        self.connections: Dict[str, set] = defaultdict(set)  # user_id -> set of websockets
        self.user_ids: Dict[object, str] = {}  # websocket -> user_id
    
    def add_connection(self, websocket, user_id: str):
        self.connections[user_id].add(websocket)
        self.user_ids[websocket] = user_id
    
    def remove_connection(self, websocket):
        user_id = self.user_ids.pop(websocket, None)
        if user_id:
            self.connections[user_id].discard(websocket)
            if not self.connections[user_id]:
                del self.connections[user_id]
    
    def get_user_websockets(self, user_id: str) -> Set:
        return self.connections.get(user_id, set())
    
    def get_user_id(self, websocket) -> Optional[str]:
        return self.user_ids.get(websocket)
    
    async def send_to_user(self, user_id: str, message: ProtocolMessage):
        """Send message to all connections of a user"""
        if user_id in self.connections:
            tasks = []
            for ws in self.connections[user_id]:
                tasks.append(self._safe_send(ws, message.to_json()))
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def send_to_users(self, user_ids: list, message: ProtocolMessage):
        """Send message to multiple users"""
        for uid in user_ids:
            await self.send_to_user(uid, message)
    
    async def broadcast(self, message: ProtocolMessage, exclude_user: str = None):
        """Broadcast message to all connected users"""
        tasks = []
        for user_id in self.connections.keys():
            if user_id != exclude_user:
                tasks.append(self.send_to_user(user_id, message))
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _safe_send(self, websocket, data: str):
        try:
            await websocket.send(data)
        except Exception:
            pass  # Connection likely closed


class MessageHandler:
    """Handles incoming messages and routes them appropriately"""
    
    def __init__(self, db: Database, conn_manager: ConnectionManager):
        self.db = db
        self.conn_manager = conn_manager
        self.ph = PasswordHasher()
        self.files_dir = Path(__file__).parent.parent / 'files'
        self.files_dir.mkdir(exist_ok=True)
        
        # Message type handlers
        self.handlers = {
            MessageType.AUTH_REGISTER.value: self.handle_register,
            MessageType.AUTH_LOGIN.value: self.handle_login,
            MessageType.AUTH_LOGOUT.value: self.handle_logout,
            MessageType.PRESENCE_UPDATE.value: self.handle_presence,
            MessageType.USER_LIST.value: self.handle_user_list,
            MessageType.CONTACT_ADD.value: self.handle_contact_add,
            MessageType.CONTACT_LIST.value: self.handle_contact_list,
            MessageType.CHAT_CREATE.value: self.handle_chat_create,
            MessageType.CHAT_LIST.value: self.handle_chat_list,
            MessageType.MESSAGE_SEND.value: self.handle_message_send,
            MessageType.MESSAGE_HISTORY.value: self.handle_message_history,
            MessageType.MESSAGE_READ.value: self.handle_message_read,
            MessageType.TYPING_START.value: self.handle_typing_start,
            MessageType.TYPING_STOP.value: self.handle_typing_stop,
            MessageType.GROUP_CREATE.value: self.handle_group_create,
            MessageType.GROUP_INFO.value: self.handle_group_info,
            MessageType.FILE_UPLOAD_START.value: self.handle_file_upload_start,
            MessageType.HEARTBEAT.value: self.handle_heartbeat,
        }
    
    async def handle_message(self, websocket, data: str):
        """Process incoming message"""
        try:
            msg = ProtocolMessage.from_json(data)
            
            # Update session activity if authenticated
            if msg.token:
                session = await self.db.get_session_by_token(msg.token)
                if session:
                    await self.db.update_session_activity(msg.token)
                else:
                    # Invalid token
                    error_msg = create_message(
                        MessageType.ERROR,
                        {'error': 'Invalid or expired token'},
                        sender='server'
                    )
                    await websocket.send(error_msg.to_json())
                    return
            
            handler = self.handlers.get(msg.type)
            if handler:
                await handler(websocket, msg)
            else:
                # Unknown message type
                error_msg = create_message(
                    MessageType.ERROR,
                    {'error': f'Unknown message type: {msg.type}'},
                    sender='server'
                )
                await websocket.send(error_msg.to_json())
                
        except json.JSONDecodeError as e:
            error_msg = create_message(
                MessageType.ERROR,
                {'error': f'Invalid JSON: {str(e)}'},
                sender='server'
            )
            await websocket.send(error_msg.to_json())
        except Exception as e:
            print(f"Error handling message: {e}")
            error_msg = create_message(
                MessageType.ERROR,
                {'error': f'Internal server error: {str(e)}'},
                sender='server'
            )
            await websocket.send(error_msg.to_json())
    
    async def handle_register(self, websocket, msg: ProtocolMessage):
        """Handle user registration"""
        payload = msg.payload
        username = payload.get('username', '').strip()
        password = payload.get('password', '')
        display_name = payload.get('display_name', username)
        
        # Validate input
        if not username or len(username) < 3:
            response = create_message(
                MessageType.AUTH_REGISTER,
                {'success': False, 'error': 'Username must be at least 3 characters'},
                sender='server'
            )
            await websocket.send(response.to_json())
            return
        
        if not password or len(password) < 6:
            response = create_message(
                MessageType.AUTH_REGISTER,
                {'success': False, 'error': 'Password must be at least 6 characters'},
                sender='server'
            )
            await websocket.send(response.to_json())
            return
        
        # Check if registration is allowed
        allow_reg = await self.db.get_setting('allow_registration', 'true')
        if allow_reg.lower() != 'true':
            response = create_message(
                MessageType.AUTH_REGISTER,
                {'success': False, 'error': 'Registration is currently disabled'},
                sender='server'
            )
            await websocket.send(response.to_json())
            return
        
        # Check if user exists
        existing = await self.db.get_user_by_username(username)
        if existing:
            response = create_message(
                MessageType.AUTH_REGISTER,
                {'success': False, 'error': 'Username already exists'},
                sender='server'
            )
            await websocket.send(response.to_json())
            return
        
        # Create user
        user_id = str(uuid.uuid4())
        password_hash = self.ph.hash(password)
        
        success = await self.db.create_user(user_id, username, password_hash, display_name)
        if success:
            response = create_message(
                MessageType.AUTH_REGISTER,
                {'success': True, 'user_id': user_id, 'username': username},
                sender='server'
            )
            await websocket.send(response.to_json())
            
            # Notify other clients about new user
            await self.conn_manager.broadcast(
                create_message(
                    MessageType.USER_LIST,
                    {'users': [await self._get_user_info(user_id)]},
                    sender='server'
                )
            )
        else:
            response = create_message(
                MessageType.AUTH_REGISTER,
                {'success': False, 'error': 'Failed to create user'},
                sender='server'
            )
            await websocket.send(response.to_json())
    
    async def handle_login(self, websocket, msg: ProtocolMessage):
        """Handle user login"""
        payload = msg.payload
        username = payload.get('username', '').strip()
        password = payload.get('password', '')
        device_id = payload.get('device_id')
        device_name = payload.get('device_name', 'Unknown Device')
        
        user = await self.db.get_user_by_username(username)
        if not user:
            response = create_message(
                MessageType.AUTH_LOGIN,
                {'success': False, 'error': 'Invalid username or password'},
                sender='server'
            )
            await websocket.send(response.to_json())
            return
        
        # Verify password
        try:
            self.ph.verify(user['password_hash'], password)
        except Exception:
            response = create_message(
                MessageType.AUTH_LOGIN,
                {'success': False, 'error': 'Invalid username or password'},
                sender='server'
            )
            await websocket.send(response.to_json())
            return
        
        # Create session
        session_id = str(uuid.uuid4())
        token = str(uuid.uuid4()) + str(uuid.uuid4())
        
        # Get session timeout
        timeout_str = await self.db.get_setting('session_timeout', '604800')
        timeout = int(timeout_str)
        expires_at = time.time() + timeout
        
        await self.db.create_session(
            session_id, user['id'], token, device_id, device_name, expires_at
        )
        
        # Update user status
        await self.db.update_user_status(user['id'], 'online')
        
        # Add to connection manager
        self.conn_manager.add_connection(websocket, user['id'])
        
        # Get user's chats
        chats = await self.db.get_user_chats(user['id'])
        contacts = await self.db.get_contacts(user['id'])
        
        response = create_message(
            MessageType.AUTH_LOGIN,
            {
                'success': True,
                'token': token,
                'user_id': user['id'],
                'username': user['username'],
                'display_name': user['display_name'],
                'chats': chats,
                'contacts': contacts
            },
            sender='server'
        )
        await websocket.send(response.to_json())
        
        # Broadcast presence update
        await self.conn_manager.broadcast(
            create_message(
                MessageType.PRESENCE_STATUS,
                {'user_id': user['id'], 'status': 'online'},
                sender='server'
            ),
            exclude_user=user['id']
        )
    
    async def handle_logout(self, websocket, msg: ProtocolMessage):
        """Handle user logout"""
        user_id = self.conn_manager.get_user_id(websocket)
        if user_id:
            await self.db.update_user_status(user_id, 'offline')
            self.conn_manager.remove_connection(websocket)
            
            if msg.token:
                await self.db.delete_session(msg.token)
            
            # Broadcast presence update
            await self.conn_manager.broadcast(
                create_message(
                    MessageType.PRESENCE_STATUS,
                    {'user_id': user_id, 'status': 'offline'},
                    sender='server'
                ),
                exclude_user=user_id
            )
    
    async def handle_presence(self, websocket, msg: ProtocolMessage):
        """Handle presence update"""
        user_id = self.conn_manager.get_user_id(websocket)
        if user_id:
            status = msg.payload.get('status', 'online')
            await self.db.update_user_status(user_id, status)
            
            await self.conn_manager.broadcast(
                create_message(
                    MessageType.PRESENCE_STATUS,
                    {'user_id': user_id, 'status': status},
                    sender='server'
                ),
                exclude_user=user_id
            )
    
    async def handle_user_list(self, websocket, msg: ProtocolMessage):
        """Handle request for user list"""
        users = await self.db.get_all_users()
        user_list = []
        for user in users:
            user_list.append(await self._get_user_info(user['id']))
        
        response = create_message(
            MessageType.USER_LIST,
            {'users': user_list},
            sender='server'
        )
        await websocket.send(response.to_json())
    
    async def handle_contact_add(self, websocket, msg: ProtocolMessage):
        """Handle adding a contact"""
        user_id = self.conn_manager.get_user_id(websocket)
        if not user_id:
            return
        
        contact_id = msg.payload.get('contact_id')
        if contact_id:
            success = await self.db.add_contact(user_id, contact_id)
            response = create_message(
                MessageType.CONTACT_ADD,
                {'success': success, 'contact_id': contact_id},
                sender='server'
            )
            await websocket.send(response.to_json())
    
    async def handle_contact_list(self, websocket, msg: ProtocolMessage):
        """Handle request for contact list"""
        user_id = self.conn_manager.get_user_id(websocket)
        if not user_id:
            return
        
        contacts = await self.db.get_contacts(user_id)
        response = create_message(
            MessageType.CONTACT_LIST,
            {'contacts': contacts},
            sender='server'
        )
        await websocket.send(response.to_json())
    
    async def handle_chat_create(self, websocket, msg: ProtocolMessage):
        """Handle creating a new chat"""
        user_id = self.conn_manager.get_user_id(websocket)
        if not user_id:
            return
        
        chat_type = msg.payload.get('type', 'private')
        name = msg.payload.get('name')
        members = msg.payload.get('members', [user_id])
        
        chat_id = str(uuid.uuid4())
        
        # Create chat
        success = await self.db.create_chat(chat_id, name, chat_type, user_id)
        if success:
            # Add members
            for member_id in members:
                role = 'owner' if member_id == user_id else 'member'
                await self.db.add_chat_member(chat_id, member_id, role)
            
            # Notify members
            chat_info = await self.db.get_chat(chat_id)
            chat_members = await self.db.get_chat_members(chat_id)
            
            for member in chat_members:
                member_msg = create_message(
                    MessageType.CHAT_CREATE,
                    {
                        'chat': chat_info,
                        'members': chat_members
                    },
                    sender='server'
                )
                await self.conn_manager.send_to_user(member['user_id'], member_msg)
    
    async def handle_chat_list(self, websocket, msg: ProtocolMessage):
        """Handle request for chat list"""
        user_id = self.conn_manager.get_user_id(websocket)
        if not user_id:
            return
        
        chats = await self.db.get_user_chats(user_id)
        response = create_message(
            MessageType.CHAT_LIST,
            {'chats': chats},
            sender='server'
        )
        await websocket.send(response.to_json())
    
    async def handle_message_send(self, websocket, msg: ProtocolMessage):
        """Handle sending a message"""
        user_id = self.conn_manager.get_user_id(websocket)
        if not user_id:
            return
        
        chat_id = msg.payload.get('chat_id')
        content = msg.payload.get('content', '')
        content_type = msg.payload.get('content_type', 'text')
        reply_to = msg.payload.get('reply_to')
        
        if not chat_id or not content:
            return
        
        # Check max message length
        max_len_str = await self.db.get_setting('max_message_length', '4096')
        max_len = int(max_len_str)
        if len(content) > max_len:
            error_msg = create_message(
                MessageType.ERROR,
                {'error': f'Message too long (max {max_len} characters)'},
                sender='server'
            )
            await websocket.send(error_msg.to_json())
            return
        
        # Create message
        message_id = str(uuid.uuid4())
        success = await self.db.create_message(
            message_id, chat_id, user_id, content, content_type, reply_to
        )
        
        if success:
            # Get full message info
            messages = await self.db.get_messages(chat_id, limit=1)
            message_info = messages[0] if messages else None
            
            # Get chat members to notify
            members = await self.db.get_chat_members(chat_id)
            member_ids = [m['user_id'] for m in members]
            
            # Send to all members
            for member_id in member_ids:
                message_msg = create_message(
                    MessageType.MESSAGE_SEND,
                    {
                        'message': message_info,
                        'chat_id': chat_id
                    },
                    sender='server'
                )
                await self.conn_manager.send_to_user(member_id, message_msg)
    
    async def handle_message_history(self, websocket, msg: ProtocolMessage):
        """Handle request for message history"""
        user_id = self.conn_manager.get_user_id(websocket)
        if not user_id:
            return
        
        chat_id = msg.payload.get('chat_id')
        limit = msg.payload.get('limit', 50)
        before = msg.payload.get('before')
        
        if not chat_id:
            return
        
        # Check if user is member of chat
        members = await self.db.get_chat_members(chat_id)
        member_ids = [m['user_id'] for m in members]
        if user_id not in member_ids:
            error_msg = create_message(
                MessageType.ERROR,
                {'error': 'Access denied to this chat'},
                sender='server'
            )
            await websocket.send(error_msg.to_json())
            return
        
        messages = await self.db.get_messages(chat_id, limit, before)
        
        # Get unread count
        unread = await self.db.get_unread_count(chat_id, user_id)
        
        response = create_message(
            MessageType.MESSAGE_HISTORY,
            {
                'chat_id': chat_id,
                'messages': messages,
                'unread_count': unread
            },
            sender='server'
        )
        await websocket.send(response.to_json())
    
    async def handle_message_read(self, websocket, msg: ProtocolMessage):
        """Handle marking messages as read"""
        user_id = self.conn_manager.get_user_id(websocket)
        if not user_id:
            return
        
        chat_id = msg.payload.get('chat_id')
        message_ids = msg.payload.get('message_ids', [])
        
        if chat_id:
            # Mark all messages in chat as read
            messages = await self.db.get_messages(chat_id, limit=1000)
            for m in messages:
                await self.db.mark_message_read(m['id'], user_id)
            
            # Notify sender
            for m in messages:
                if m['sender_id'] != user_id:
                    read_msg = create_message(
                        MessageType.MESSAGE_READ,
                        {
                            'chat_id': chat_id,
                            'message_id': m['id'],
                            'read_by': user_id
                        },
                        sender='server'
                    )
                    await self.conn_manager.send_to_user(m['sender_id'], read_msg)
    
    async def handle_typing_start(self, websocket, msg: ProtocolMessage):
        """Handle typing indicator start"""
        await self._handle_typing(websocket, msg, True)
    
    async def handle_typing_stop(self, websocket, msg: ProtocolMessage):
        """Handle typing indicator stop"""
        await self._handle_typing(websocket, msg, False)
    
    async def _handle_typing(self, websocket, msg: ProtocolMessage, is_typing: bool):
        user_id = self.conn_manager.get_user_id(websocket)
        if not user_id:
            return
        
        chat_id = msg.payload.get('chat_id')
        if chat_id:
            typing_msg = create_message(
                MessageType.TYPING_START if is_typing else MessageType.TYPING_STOP,
                {'chat_id': chat_id, 'user_id': user_id},
                sender='server'
            )
            
            # Send to other chat members
            members = await self.db.get_chat_members(chat_id)
            for member in members:
                if member['user_id'] != user_id:
                    await self.conn_manager.send_to_user(member['user_id'], typing_msg)
    
    async def handle_group_create(self, websocket, msg: ProtocolMessage):
        """Handle creating a group chat"""
        user_id = self.conn_manager.get_user_id(websocket)
        if not user_id:
            return
        
        name = msg.payload.get('name', 'New Group')
        members = msg.payload.get('members', [user_id])
        
        # Ensure creator is in members
        if user_id not in members:
            members.append(user_id)
        
        chat_id = str(uuid.uuid4())
        
        # Create group chat
        success = await self.db.create_chat(chat_id, name, 'group', user_id)
        if success:
            # Add members
            for member_id in members:
                role = 'owner' if member_id == user_id else 'member'
                await self.db.add_chat_member(chat_id, member_id, role)
            
            # Notify members
            chat_info = await self.db.get_chat(chat_id)
            chat_members = await self.db.get_chat_members(chat_id)
            
            for member in chat_members:
                member_msg = create_message(
                    MessageType.GROUP_CREATE,
                    {
                        'chat': chat_info,
                        'members': chat_members
                    },
                    sender='server'
                )
                await self.conn_manager.send_to_user(member['user_id'], member_msg)
    
    async def handle_group_info(self, websocket, msg: ProtocolMessage):
        """Handle request for group info"""
        user_id = self.conn_manager.get_user_id(websocket)
        if not user_id:
            return
        
        chat_id = msg.payload.get('chat_id')
        if not chat_id:
            return
        
        chat = await self.db.get_chat(chat_id)
        if not chat:
            return
        
        members = await self.db.get_chat_members(chat_id)
        
        response = create_message(
            MessageType.GROUP_INFO,
            {
                'chat': chat,
                'members': members
            },
            sender='server'
        )
        await websocket.send(response.to_json())
    
    async def handle_file_upload_start(self, websocket, msg: ProtocolMessage):
        """Handle file upload initiation"""
        user_id = self.conn_manager.get_user_id(websocket)
        if not user_id:
            return
        
        filename = msg.payload.get('filename')
        filesize = msg.payload.get('filesize', 0)
        mime_type = msg.payload.get('mime_type')
        
        if not filename:
            return
        
        # Check file size limit
        max_size_str = await self.db.get_setting('max_file_size', '104857600')
        max_size = int(max_size_str)
        if filesize > max_size:
            error_msg = create_message(
                MessageType.ERROR,
                {'error': f'File too large (max {max_size // 1024 // 1024}MB)'},
                sender='server'
            )
            await websocket.send(error_msg.to_json())
            return
        
        # Generate unique filepath
        file_id = str(uuid.uuid4())
        ext = Path(filename).suffix
        safe_filename = f"{file_id}{ext}"
        filepath = self.files_dir / safe_filename
        
        response = create_message(
            MessageType.FILE_UPLOAD_START,
            {
                'file_id': file_id,
                'filepath': str(filepath),
                'accepted': True
            },
            sender='server'
        )
        await websocket.send(response.to_json())
    
    async def handle_heartbeat(self, websocket, msg: ProtocolMessage):
        """Handle heartbeat/ping"""
        user_id = self.conn_manager.get_user_id(websocket)
        if user_id:
            response = create_message(
                MessageType.HEARTBEAT_ACK,
                {'timestamp': time.time()},
                sender='server'
            )
            await websocket.send(response.to_json())
    
    async def _get_user_info(self, user_id: str) -> Dict:
        """Get user info dict"""
        user = await self.db.get_user_by_id(user_id)
        if user:
            return {
                'id': user['id'],
                'username': user['username'],
                'display_name': user['display_name'],
                'status': user['status'],
                'avatar': user.get('avatar'),
                'last_seen': user.get('last_seen', 0)
            }
        return {}
