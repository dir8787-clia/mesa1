"""
LocalNet Messenger - Server Module
WebSocket server with authentication, messaging, and file transfer
"""

import asyncio
import json
import logging
import signal
import sys
import time
import hashlib
import secrets
import socket
from pathlib import Path
from typing import Dict, Set, Optional, Any
from datetime import datetime, timedelta

# Add parent directory to path for imports
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

import aiohttp
from aiohttp import web
from zeroconf import Zeroconf, ServiceInfo
from argon2 import PasswordHasher

from server.database import Database
from shared.protocol import MessageType, ProtocolMessage

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ClientConnection:
    """Represents a connected client"""
    
    def __init__(self, ws: web.WebSocketResponse, user_id: Optional[int] = None, username: Optional[str] = None):
        self.ws = ws
        self.user_id = user_id
        self.username = username
        self.last_seen = time.time()
        self.is_authenticated = False
    
    def update_last_seen(self):
        self.last_seen = time.time()


class LocalNetServer:
    """LocalNet Messenger Server"""
    
    def __init__(self, host: str = "0.0.0.0", port: int = 8765, data_dir: str = "server/data"):
        self.host = host
        self.port = port
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.db = Database(str(self.data_dir / "messenger.db"))
        self.ph = PasswordHasher()
        
        self.connections: Dict[int, ClientConnection] = {}  # user_id -> connection
        self.ws_connections: Set[web.WebSocketResponse] = set()  # all WS connections
        self.user_sessions: Dict[str, int] = {}  # token -> user_id
        
        self.app = web.Application()
        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None
        
        self.zeroconf: Optional[Zeroconf] = None
        self.service_info: Optional[ServiceInfo] = None
        
        self._shutdown_event = asyncio.Event()
        self._heartbeat_interval = 30  # seconds
    
    async def start(self):
        """Start the server"""
        await self.db.connect()
        
        # Setup routes
        self.app.router.add_get('/ws', self.websocket_handler)
        self.app.router.add_get('/health', self.health_handler)
        
        # Start HTTP server
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, self.host, self.port)
        await self.site.start()
        
        logger.info(f"WebSocket server started at ws://{self.host}:{self.port}/ws")
        
        # Register mDNS service
        await self._register_mdns()
        
        logger.info("Server is ready to accept connections")
    
    async def stop(self):
        """Stop the server"""
        logger.info("Shutting down server...")
        
        # Close all WebSocket connections
        for conn in list(self.ws_connections):
            try:
                await conn.close()
            except:
                pass
        
        # Unregister mDNS
        await self._unregister_mdns()
        
        if self.runner:
            await self.runner.cleanup()
        
        await self.db.close()
        logger.info("Server stopped")
    
    async def _register_mdns(self):
        """Register mDNS service for auto-discovery"""
        try:
            self.zeroconf = Zeroconf()
            
            # Get local IP
            local_ip = self.host if self.host != "0.0.0.0" else "127.0.0.1"
            
            self.service_info = ServiceInfo(
                "_localnet-msg._tcp.local.",
                f"LocalNet Messenger._localnet-msg._tcp.local.",
                addresses=[socket.inet_aton(local_ip)],
                port=self.port,
                properties={
                    b'version': b'1.0',
                    b'protocol': b'websocket'
                }
            )
            
            await asyncio.get_event_loop().run_in_executor(None, self.zeroconf.register_service, self.service_info)
            logger.info(f"mDNS service registered: _localnet-msg._tcp.local. at {local_ip}:{self.port}")
        except Exception as e:
            logger.warning(f"Failed to register mDNS service: {e}")
    
    async def _unregister_mdns(self):
        """Unregister mDNS service"""
        if self.zeroconf and self.service_info:
            try:
                await asyncio.get_event_loop().run_in_executor(None, self.zeroconf.unregister_service, self.service_info)
                self.zeroconf.close()
            except Exception as e:
                logger.warning(f"Failed to unregister mDNS service: {e}")
    
    async def health_handler(self, request: web.Request) -> web.Response:
        """Health check endpoint"""
        return web.json_response({
            "status": "ok",
            "connections": len([c for c in self.connections.values() if c.is_authenticated]),
            "users": len(self.connections)
        })
    
    async def websocket_handler(self, request: web.Request) -> web.WebSocketResponse:
        """Handle WebSocket connections"""
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        
        conn = ClientConnection(ws)
        self.ws_connections.add(ws)
        
        logger.info(f"New WebSocket connection from {request.remote}")
        
        try:
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    await self._handle_message(conn, msg.data)
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error(f"WebSocket error: {ws.exception()}")
                    break
        finally:
            self.ws_connections.discard(ws)
            if conn.user_id and conn.user_id in self.connections:
                del self.connections[conn.user_id]
            await self._broadcast_presence()
        
        logger.info(f"WebSocket connection closed: {request.remote}")
        return ws
    
    async def _handle_message(self, conn: ClientConnection, data: str):
        """Handle incoming WebSocket message"""
        try:
            msg = ProtocolMessage.from_json(data)
            conn.update_last_seen()
            
            handlers = {
                MessageType.AUTH_REGISTER.value: self._handle_register,
                MessageType.AUTH_LOGIN.value: self._handle_login,
                MessageType.AUTH_LOGOUT.value: self._handle_logout,
                MessageType.MESSAGE_SEND.value: self._handle_message_send,
                MessageType.CHAT_LIST.value: self._handle_chat_list,
                MessageType.CHAT_CREATE.value: self._handle_chat_create,
                MessageType.GROUP_CREATE.value: self._handle_group_create,
                MessageType.USER_LIST.value: self._handle_user_list,
                MessageType.PING.value: self._handle_ping,
            }
            
            handler = handlers.get(msg.type)
            if handler:
                response = await handler(conn, msg)
                if response:
                    await conn.ws.send_str(response.to_json())
            else:
                error_msg = ProtocolMessage.create_error(f"Unknown message type: {msg.type}", "UNKNOWN_TYPE", msg.id)
                await conn.ws.send_str(error_msg.to_json())
                
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON: {e}")
            error_msg = ProtocolMessage.create_error("Invalid JSON format", "INVALID_JSON")
            await conn.ws.send_str(error_msg.to_json())
        except Exception as e:
            logger.error(f"Error handling message: {e}", exc_info=True)
            error_msg = ProtocolMessage.create_error(str(e), "INTERNAL_ERROR")
            await conn.ws.send_str(error_msg.to_json())
    
    async def _handle_register(self, conn: ClientConnection, msg: ProtocolMessage) -> Optional[ProtocolMessage]:
        """Handle user registration"""
        username = msg.payload.get("username", "").strip()
        password = msg.payload.get("password", "")
        display_name = msg.payload.get("display_name", username)
        
        if not username or len(username) < 3:
            return ProtocolMessage.create_error("Username must be at least 3 characters", "INVALID_USERNAME", msg.id)
        
        if not password or len(password) < 6:
            return ProtocolMessage.create_error("Password must be at least 6 characters", "INVALID_PASSWORD", msg.id)
        
        # Check if user exists
        existing = await self.db.fetchone("SELECT id FROM users WHERE username = ?", (username,))
        if existing:
            return ProtocolMessage.create_error("Username already exists", "USER_EXISTS", msg.id)
        
        # Create user
        password_hash = self.ph.hash(password)
        created_at = time.time()
        
        await self.db.execute(
            "INSERT INTO users (username, display_name, password_hash, created_at) VALUES (?, ?, ?, ?)",
            (username, display_name, password_hash, created_at)
        )
        
        logger.info(f"User registered: {username}")
        
        return ProtocolMessage(MessageType.AUTH_REGISTER, {"success": True, "username": username}, msg_id=msg.id)
    
    async def _handle_login(self, conn: ClientConnection, msg: ProtocolMessage) -> Optional[ProtocolMessage]:
        """Handle user login"""
        username = msg.payload.get("username", "").strip()
        password = msg.payload.get("password", "")
        
        # Get user
        user = await self.db.fetchone("SELECT * FROM users WHERE username = ?", (username,))
        if not user:
            return ProtocolMessage.create_error("Invalid username or password", "INVALID_CREDENTIALS", msg.id)
        
        # Verify password
        try:
            self.ph.verify(user["password_hash"], password)
        except Exception:
            return ProtocolMessage.create_error("Invalid username or password", "INVALID_CREDENTIALS", msg.id)
        
        # Create session token
        token = secrets.token_urlsafe(32)
        expires_at = time.time() + (30 * 24 * 60 * 60)  # 30 days
        
        await self.db.execute(
            "INSERT INTO sessions (user_id, token, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (user["id"], token, time.time(), expires_at)
        )
        
        # Update connection
        conn.user_id = user["id"]
        conn.username = username
        conn.is_authenticated = True
        self.connections[user["id"]] = conn
        self.user_sessions[token] = user["id"]
        
        # Update user status
        await self.db.execute(
            "UPDATE users SET status = ?, last_seen = ? WHERE id = ?",
            ("online", time.time(), user["id"])
        )
        
        logger.info(f"User logged in: {username}")
        
        # Broadcast presence update
        await self._broadcast_presence()
        
        return ProtocolMessage(
            MessageType.AUTH_LOGIN,
            {
                "success": True,
                "user_id": user["id"],
                "username": username,
                "display_name": user["display_name"],
                "token": token
            },
            msg_id=msg.id
        )
    
    async def _handle_logout(self, conn: ClientConnection, msg: ProtocolMessage) -> Optional[ProtocolMessage]:
        """Handle user logout"""
        if conn.user_id:
            # Remove session
            await self.db.execute("DELETE FROM sessions WHERE user_id = ?", (conn.user_id,))
            
            # Update user status
            await self.db.execute(
                "UPDATE users SET status = ?, last_seen = ? WHERE id = ?",
                ("offline", time.time(), conn.user_id)
            )
            
            # Remove connection
            if conn.user_id in self.connections:
                del self.connections[conn.user_id]
            
            # Remove token
            for token, user_id in list(self.user_sessions.items()):
                if user_id == conn.user_id:
                    del self.user_sessions[token]
            
            conn.user_id = None
            conn.username = None
            conn.is_authenticated = False
            
            await self._broadcast_presence()
            logger.info(f"User logged out: {conn.username or 'unknown'}")
        
        return ProtocolMessage(MessageType.AUTH_LOGOUT, {"success": True}, msg_id=msg.id)
    
    async def _handle_message_send(self, conn: ClientConnection, msg: ProtocolMessage) -> Optional[ProtocolMessage]:
        """Handle sending a message"""
        if not conn.is_authenticated:
            return ProtocolMessage.create_error("Not authenticated", "AUTH_REQUIRED", msg.id)
        
        chat_id = msg.payload.get("chat_id")
        content = msg.payload.get("content", "")
        message_type = msg.payload.get("type", "text")
        reply_to = msg.payload.get("reply_to")
        
        if not chat_id or not content:
            return ProtocolMessage.create_error("Invalid message data", "INVALID_DATA", msg.id)
        
        # Check chat membership
        member = await self.db.fetchone(
            "SELECT 1 FROM chat_members WHERE chat_id = ? AND user_id = ?",
            (chat_id, conn.user_id)
        )
        if not member:
            return ProtocolMessage.create_error("Not a member of this chat", "ACCESS_DENIED", msg.id)
        
        # Save message
        created_at = time.time()
        cursor = await self.db.execute(
            "INSERT INTO messages (chat_id, sender_id, content, message_type, reply_to, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (chat_id, conn.user_id, content, message_type, reply_to, created_at)
        )
        message_id = cursor.lastrowid
        
        # Get chat members to notify
        members = await self.db.fetchall("SELECT user_id FROM chat_members WHERE chat_id = ?", (chat_id,))
        
        # Prepare message data
        message_data = {
            "id": message_id,
            "chat_id": chat_id,
            "sender_id": conn.user_id,
            "sender_username": conn.username,
            "content": content,
            "type": message_type,
            "reply_to": reply_to,
            "created_at": created_at
        }
        
        # Send to all chat members
        response = ProtocolMessage(MessageType.MESSAGE_SEND, message_data, msg_id=msg.id)
        for member in members:
            user_id = member["user_id"]
            if user_id in self.connections:
                await self.connections[user_id].ws.send_str(response.to_json())
        
        return None  # Response already sent
    
    async def _handle_chat_list(self, conn: ClientConnection, msg: ProtocolMessage) -> Optional[ProtocolMessage]:
        """Handle chat list request"""
        if not conn.is_authenticated:
            return ProtocolMessage.create_error("Not authenticated", "AUTH_REQUIRED", msg.id)
        
        chats = await self.db.fetchall("""
            SELECT c.*, u.username as creator_username
            FROM chats c
            JOIN chat_members cm ON c.id = cm.chat_id
            LEFT JOIN users u ON c.created_by = u.id
            WHERE cm.user_id = ?
        """, (conn.user_id,))
        
        chat_list = []
        for chat in chats:
            # Get members
            members = await self.db.fetchall("""
                SELECT u.id, u.username, u.display_name, u.status
                FROM users u
                JOIN chat_members cm ON u.id = cm.user_id
                WHERE cm.chat_id = ?
            """, (chat["id"],))
            
            # Get last message
            last_msg = await self.db.fetchone("""
                SELECT m.*, u.username as sender_username
                FROM messages m
                JOIN users u ON m.sender_id = u.id
                WHERE m.chat_id = ? AND m.deleted_at IS NULL
                ORDER BY m.created_at DESC LIMIT 1
            """, (chat["id"],))
            
            chat_list.append({
                "id": chat["id"],
                "type": chat["chat_type"],
                "name": chat["name"],
                "avatar_url": chat["avatar_url"],
                "created_by": chat["created_by"],
                "creator_username": chat["creator_username"],
                "members": [{"id": m["id"], "username": m["username"], "display_name": m["display_name"], "status": m["status"]} for m in members],
                "last_message": {
                    "id": last_msg["id"],
                    "sender_id": last_msg["sender_id"],
                    "sender_username": last_msg["sender_username"],
                    "content": last_msg["content"],
                    "created_at": last_msg["created_at"]
                } if last_msg else None
            })
        
        return ProtocolMessage(MessageType.CHAT_LIST, {"chats": chat_list}, msg_id=msg.id)
    
    async def _handle_chat_create(self, conn: ClientConnection, msg: ProtocolMessage) -> Optional[ProtocolMessage]:
        """Handle creating a new chat (personal or group)"""
        if not conn.is_authenticated:
            return ProtocolMessage.create_error("Not authenticated", "AUTH_REQUIRED", msg.id)
        
        chat_type = msg.payload.get("type", "personal")
        name = msg.payload.get("name")
        member_ids = msg.payload.get("member_ids", [])
        
        if chat_type == "personal" and len(member_ids) == 1:
            # Check if personal chat already exists
            other_user_id = member_ids[0]
            existing = await self.db.fetchone("""
                SELECT c.id FROM chats c
                JOIN chat_members cm1 ON c.id = cm1.chat_id
                JOIN chat_members cm2 ON c.id = cm2.chat_id
                WHERE c.chat_type = 'personal'
                AND cm1.user_id = ? AND cm2.user_id = ?
            """, (conn.user_id, other_user_id))
            
            if existing:
                return ProtocolMessage(MessageType.CHAT_CREATE, {"chat_id": existing["id"], "exists": True}, msg_id=msg.id)
        
        # Create chat
        created_at = time.time()
        cursor = await self.db.execute(
            "INSERT INTO chats (chat_type, name, created_by, created_at) VALUES (?, ?, ?, ?)",
            (chat_type, name, conn.user_id, created_at)
        )
        chat_id = cursor.lastrowid
        
        # Add members
        members_to_add = [conn.user_id] + member_ids
        for member_id in members_to_add:
            await self.db.execute(
                "INSERT INTO chat_members (chat_id, user_id, joined_at) VALUES (?, ?, ?)",
                (chat_id, member_id, time.time())
            )
        
        # Notify members
        chat_data = {
            "id": chat_id,
            "type": chat_type,
            "name": name,
            "member_ids": members_to_add,
            "created_by": conn.user_id
        }
        
        response = ProtocolMessage(MessageType.CHAT_CREATE, chat_data, msg_id=msg.id)
        for member_id in members_to_add:
            if member_id in self.connections:
                await self.connections[member_id].ws.send_str(response.to_json())
        
        return None
    
    async def _handle_group_create(self, conn: ClientConnection, msg: ProtocolMessage) -> Optional[ProtocolMessage]:
        """Handle creating a group chat"""
        if not conn.is_authenticated:
            return ProtocolMessage.create_error("Not authenticated", "AUTH_REQUIRED", msg.id)
        
        name = msg.payload.get("name", "New Group")
        member_ids = msg.payload.get("member_ids", [])
        
        # Create group chat
        created_at = time.time()
        cursor = await self.db.execute(
            "INSERT INTO chats (chat_type, name, created_by, created_at) VALUES (?, ?, ?, ?)",
            ("group", name, conn.user_id, created_at)
        )
        chat_id = cursor.lastrowid
        
        # Add owner as member with admin role
        await self.db.execute(
            "INSERT INTO chat_members (chat_id, user_id, role, joined_at) VALUES (?, ?, ?, ?)",
            (chat_id, conn.user_id, "admin", time.time())
        )
        
        # Add other members
        for member_id in member_ids:
            await self.db.execute(
                "INSERT INTO chat_members (chat_id, user_id, role, joined_at) VALUES (?, ?, ?, ?)",
                (chat_id, member_id, "member", time.time())
            )
        
        # Notify all members
        members_to_notify = [conn.user_id] + member_ids
        chat_data = {
            "id": chat_id,
            "type": "group",
            "name": name,
            "owner_id": conn.user_id,
            "member_ids": members_to_notify
        }
        
        response = ProtocolMessage(MessageType.GROUP_CREATE, chat_data, msg_id=msg.id)
        for member_id in members_to_notify:
            if member_id in self.connections:
                await self.connections[member_id].ws.send_str(response.to_json())
        
        return None
    
    async def _handle_user_list(self, conn: ClientConnection, msg: ProtocolMessage) -> Optional[ProtocolMessage]:
        """Handle user list request"""
        if not conn.is_authenticated:
            return ProtocolMessage.create_error("Not authenticated", "AUTH_REQUIRED", msg.id)
        
        users = await self.db.fetchall("""
            SELECT id, username, display_name, status, last_seen
            FROM users
            WHERE id != ?
        """, (conn.user_id,))
        
        user_list = [{
            "id": u["id"],
            "username": u["username"],
            "display_name": u["display_name"],
            "status": u["status"],
            "last_seen": u["last_seen"]
        } for u in users]
        
        return ProtocolMessage(MessageType.USER_LIST, {"users": user_list}, msg_id=msg.id)
    
    async def _handle_ping(self, conn: ClientConnection, msg: ProtocolMessage) -> Optional[ProtocolMessage]:
        """Handle ping message"""
        return ProtocolMessage.create_pong(msg.id)
    
    async def _broadcast_presence(self):
        """Broadcast user presence updates to all connected clients"""
        users = []
        for user_id, conn in self.connections.items():
            if conn.is_authenticated:
                users.append({
                    "id": user_id,
                    "username": conn.username,
                    "status": "online"
                })
        
        # Also get offline users from database
        offline_users = await self.db.fetchall(
            "SELECT id, username, status FROM users WHERE status != ?",
            ("online",)
        )
        for u in offline_users:
            users.append({
                "id": u["id"],
                "username": u["username"],
                "status": u["status"]
            })
        
        msg = ProtocolMessage(MessageType.PRESENCE_UPDATE, {"users": users})
        
        for conn in self.connections.values():
            if conn.is_authenticated:
                try:
                    await conn.ws.send_str(msg.to_json())
                except:
                    pass


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="LocalNet Messenger Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8765, help="Port to bind to")
    parser.add_argument("--data-dir", default="server/data", help="Data directory")
    
    args = parser.parse_args()
    
    logger.info(f"Starting LocalNet Messenger Server on {args.host}:{args.port}")
    
    server = LocalNetServer(host=args.host, port=args.port, data_dir=args.data_dir)
    
    # Setup event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    def signal_handler():
        logger.info("Received shutdown signal")
        loop.create_task(server.stop())
        server._shutdown_event.set()
    
    # Only add signal handlers on Unix-like systems
    if sys.platform != 'win32':
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, signal_handler)
            except NotImplementedError:
                logger.debug(f"Signal handler not available for sig {sig}")
    
    try:
        loop.run_until_complete(server.start())
    except KeyboardInterrupt:
        pass
    finally:
        # Run cleanup
        if not server._shutdown_event.is_set():
            loop.run_until_complete(server.stop())
        loop.close()


if __name__ == '__main__':
    main()
