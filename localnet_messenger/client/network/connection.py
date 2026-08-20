"""
LocalNet Messenger - Client Network Module
Handles WebSocket connections, message sending/receiving, and server discovery
"""

import asyncio
import json
import logging
import socket
from typing import Dict, Any, Optional, Callable, List
from pathlib import Path
import sys

# Add parent directory to path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

import aiohttp
from zeroconf import Zeroconf, ServiceBrowser, ServiceListener

from shared.protocol import MessageType, ProtocolMessage

logger = logging.getLogger(__name__)


class ServerDiscovery(ServiceListener):
    """Discover LocalNet servers via mDNS"""
    
    def __init__(self):
        self.found_servers: List[Dict[str, Any]] = []
    
    def add_service(self, zeroconf: Zeroconf, service_type: str, name: str):
        info = zeroconf.get_service_info(service_type, name)
        if info:
            server = {
                "name": name,
                "host": socket.inet_ntoa(info.addresses[0]),
                "port": info.port,
                "properties": {k.decode(): v.decode() for k, v in info.properties.items()}
            }
            self.found_servers.append(server)
            logger.info(f"Found server: {server['host']}:{server['port']}")
    
    def remove_service(self, zeroconf: Zeroconf, service_type: str, name: str):
        self.found_servers = [s for s in self.found_servers if s["name"] != name]
        logger.info(f"Server removed: {name}")
    
    def update_service(self, zeroconf: Zeroconf, service_type: str, name: str):
        logger.info(f"Server updated: {name}")


class NetworkManager:
    """Manages network connections and communication"""
    
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self.server_host: str = "127.0.0.1"
        self.server_port: int = 8765
        self.is_connected: bool = False
        self.auth_token: Optional[str] = None
        self.user_id: Optional[int] = None
        self.username: Optional[str] = None
        
        self._message_handlers: Dict[str, Callable] = {}
        self._pending_responses: Dict[str, asyncio.Future] = {}
        self._receive_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._discovery: Optional[ServerDiscovery] = None
        self._zeroconf: Optional[Zeroconf] = None
    
    async def start(self):
        """Start the network manager"""
        self.session = aiohttp.ClientSession()
        logger.info("Network manager started")
    
    async def stop(self):
        """Stop the network manager"""
        await self.disconnect()
        
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
        
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        
        if self.session:
            await self.session.close()
            self.session = None
        
        logger.info("Network manager stopped")
    
    async def discover_servers(self, timeout: float = 3.0) -> List[Dict[str, Any]]:
        """Discover servers via mDNS"""
        self._discovery = ServerDiscovery()
        self._zeroconf = Zeroconf()
        
        browser = ServiceBrowser(self._zeroconf, "_localnet-msg._tcp.local.", self._discovery)
        
        await asyncio.sleep(timeout)
        
        browser.cancel()
        
        servers = self._discovery.found_servers.copy()
        
        return servers
    
    async def connect(self, host: str, port: int) -> bool:
        """Connect to server via WebSocket"""
        self.server_host = host
        self.server_port = port
        
        try:
            url = f"ws://{host}:{port}/ws"
            self.ws = await self.session.ws_connect(url)
            self.is_connected = True
            
            logger.info(f"Connected to server at {host}:{port}")
            
            # Start receive task
            self._receive_task = asyncio.create_task(self._receive_messages())
            
            # Start heartbeat
            self._heartbeat_task = asyncio.create_task(self._send_heartbeat())
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect: {e}")
            self.is_connected = False
            return False
    
    async def disconnect(self):
        """Disconnect from server"""
        if self.ws:
            await self.ws.close()
            self.ws = None
        
        self.is_connected = False
        logger.info("Disconnected from server")
    
    async def _receive_messages(self):
        """Receive and process messages from server"""
        try:
            async for msg in self.ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    await self._process_message(msg.data)
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error(f"WebSocket error: {self.ws.exception()}")
                    break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error receiving messages: {e}")
    
    async def _process_message(self, data: str):
        """Process incoming message"""
        try:
            msg = ProtocolMessage.from_json(data)
            
            # Check if we have a pending response
            if msg.id in self._pending_responses:
                future = self._pending_responses.pop(msg.id)
                if not future.done():
                    future.set_result(msg)
                return
            
            # Call registered handlers
            handler = self._message_handlers.get(msg.type)
            if handler:
                await handler(msg)
                
        except Exception as e:
            logger.error(f"Error processing message: {e}")
    
    async def _send_heartbeat(self):
        """Send periodic heartbeat"""
        while self.is_connected:
            try:
                await asyncio.sleep(30)
                if self.is_connected and self.ws:
                    ping_msg = ProtocolMessage.create_ping()
                    await self.send_message(ping_msg)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
    
    async def send_message(self, msg: ProtocolMessage, wait_for_response: bool = False, timeout: float = 5.0) -> Optional[ProtocolMessage]:
        """Send a message to server"""
        if not self.ws or not self.is_connected:
            logger.error("Not connected to server")
            return None
        
        if self.auth_token:
            msg.auth_token = self.auth_token
        
        try:
            await self.ws.send_str(msg.to_json())
            
            if wait_for_response:
                future = asyncio.Future()
                self._pending_responses[msg.id] = future
                
                try:
                    return await asyncio.wait_for(future, timeout=timeout)
                except asyncio.TimeoutError:
                    logger.warning(f"Timeout waiting for response to {msg.type}")
                    return None
                    
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return None
        
        return None
    
    def register_handler(self, msg_type: str, handler: Callable):
        """Register a message handler"""
        self._message_handlers[msg_type] = handler
    
    def unregister_handler(self, msg_type: str):
        """Unregister a message handler"""
        self._message_handlers.pop(msg_type, None)
    
    # High-level API methods
    
    async def register(self, username: str, password: str, display_name: Optional[str] = None) -> Dict[str, Any]:
        """Register a new user"""
        msg = ProtocolMessage(
            MessageType.AUTH_REGISTER,
            {
                "username": username,
                "password": password,
                "display_name": display_name or username
            }
        )
        
        response = await self.send_message(msg, wait_for_response=True)
        
        if response and response.type == MessageType.AUTH_REGISTER.value:
            return {"success": True, **response.payload}
        elif response and response.type == MessageType.ERROR.value:
            return {"success": False, "error": response.payload.get("error", "Unknown error")}
        else:
            return {"success": False, "error": "No response from server"}
    
    async def login(self, username: str, password: str) -> Dict[str, Any]:
        """Login to server"""
        msg = ProtocolMessage(
            MessageType.AUTH_LOGIN,
            {
                "username": username,
                "password": password
            }
        )
        
        response = await self.send_message(msg, wait_for_response=True)
        
        if response and response.type == MessageType.AUTH_LOGIN.value:
            self.auth_token = response.payload.get("token")
            self.user_id = response.payload.get("user_id")
            self.username = response.payload.get("username")
            return {"success": True, **response.payload}
        elif response and response.type == MessageType.ERROR.value:
            return {"success": False, "error": response.payload.get("error", "Unknown error")}
        else:
            return {"success": False, "error": "No response from server"}
    
    async def logout(self) -> Dict[str, Any]:
        """Logout from server"""
        msg = ProtocolMessage(MessageType.AUTH_LOGOUT, {})
        response = await self.send_message(msg, wait_for_response=True)
        
        if response:
            self.auth_token = None
            self.user_id = None
            self.username = None
            return {"success": True}
        
        return {"success": False}
    
    async def get_user_list(self) -> List[Dict[str, Any]]:
        """Get list of users"""
        msg = ProtocolMessage(MessageType.USER_LIST, {})
        response = await self.send_message(msg, wait_for_response=True)
        
        if response and response.type == MessageType.USER_LIST.value:
            return response.payload.get("users", [])
        
        return []
    
    async def get_chat_list(self) -> List[Dict[str, Any]]:
        """Get list of chats"""
        msg = ProtocolMessage(MessageType.CHAT_LIST, {})
        response = await self.send_message(msg, wait_for_response=True)
        
        if response and response.type == MessageType.CHAT_LIST.value:
            return response.payload.get("chats", [])
        
        return []
    
    async def create_chat(self, chat_type: str = "personal", name: Optional[str] = None, member_ids: Optional[List[int]] = None) -> Dict[str, Any]:
        """Create a new chat"""
        msg = ProtocolMessage(
            MessageType.CHAT_CREATE,
            {
                "type": chat_type,
                "name": name,
                "member_ids": member_ids or []
            }
        )
        
        response = await self.send_message(msg, wait_for_response=True)
        
        if response and response.type in [MessageType.CHAT_CREATE.value, MessageType.GROUP_CREATE.value]:
            return {"success": True, **response.payload}
        elif response and response.type == MessageType.ERROR.value:
            return {"success": False, "error": response.payload.get("error", "Unknown error")}
        
        return {"success": False, "error": "No response from server"}
    
    async def send_message_to_chat(self, chat_id: int, content: str, message_type: str = "text", reply_to: Optional[int] = None) -> Dict[str, Any]:
        """Send a message to a chat"""
        msg = ProtocolMessage(
            MessageType.MESSAGE_SEND,
            {
                "chat_id": chat_id,
                "content": content,
                "type": message_type,
                "reply_to": reply_to
            }
        )
        
        # Don't wait for response for messages, they'll come via broadcast
        await self.send_message(msg)
        
        return {"success": True}
    
    async def send_typing_indicator(self, chat_id: int, is_typing: bool = True):
        """Send typing indicator"""
        msg_type = MessageType.TYPING_START if is_typing else MessageType.TYPING_STOP
        msg = ProtocolMessage(msg_type, {"chat_id": chat_id})
        await self.send_message(msg)
