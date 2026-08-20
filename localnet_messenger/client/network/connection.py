#!/usr/bin/env python3
"""
LocalNet Messenger - Client Network Module
Handles server connection, discovery, and message routing
"""
import asyncio
import json
import time
import uuid
from typing import Optional, Dict, Any, Callable, List
from pathlib import Path
import logging

import aiohttp
from zeroconf import ServiceBrowser, Zeroconf, ServiceListener

from shared.protocol import MessageType, ProtocolMessage, create_message

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ServerDiscovery(ServiceListener):
    """Discovers LocalNet Messenger servers via mDNS"""
    
    def __init__(self):
        self.servers: List[Dict[str, Any]] = []
        self._zeroconf: Optional[Zeroconf] = None
        self._browser: Optional[ServiceBrowser] = None
    
    def start(self):
        """Start discovering servers"""
        try:
            self._zeroconf = Zeroconf()
            self._browser = ServiceBrowser(
                self._zeroconf, 
                "_localnet-msg._tcp.local.", 
                self
            )
            logger.info("Started server discovery via mDNS")
        except Exception as e:
            logger.warning(f"Could not start mDNS discovery: {e}")
    
    def stop(self):
        """Stop discovering servers"""
        if self._browser:
            self._browser.cancel()
        if self._zeroconf:
            self._zeroconf.close()
    
    def add_service(self, zeroconf, service_type, name):
        """Called when a service is added"""
        info = zeroconf.get_service_info(service_type, name)
        if info:
            server = {
                'name': name,
                'host': str(info.parsed_addresses()[0]) if info.parsed_addresses() else None,
                'port': info.port,
                'properties': info.properties
            }
            self.servers.append(server)
            logger.info(f"Found server: {server['host']}:{server['port']}")
    
    def remove_service(self, zeroconf, service_type, name):
        """Called when a service is removed"""
        self.servers = [s for s in self.servers if s['name'] != name]
        logger.info(f"Server removed: {name}")
    
    def update_service(self, zeroconf, service_type, name):
        """Called when a service is updated"""
        pass
    
    def get_servers(self) -> List[Dict[str, Any]]:
        """Get list of discovered servers"""
        return self.servers.copy()


class NetworkManager:
    """Manages network connections to the server"""
    
    def __init__(self):
        self.server_host: Optional[str] = None
        self.server_port: int = 8765
        self.session_token: Optional[str] = None
        self.user_id: Optional[str] = None
        self.username: Optional[str] = None
        
        self._session: Optional[aiohttp.ClientSession] = None
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._connected = False
        self._connecting = False
        self._message_handlers: Dict[str, Callable] = {}
        self._pending_requests: Dict[str, asyncio.Future] = {}
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._reconnect_task: Optional[asyncio.Task] = None
        self._message_queue: List[ProtocolMessage] = []  # Offline queue
        
        self.discovery = ServerDiscovery()
        
        # Connection state callbacks
        self._on_connected_callbacks: List[Callable] = []
        self._on_disconnected_callbacks: List[Callable] = []
        self._on_message_callbacks: List[Callable] = []
    
    async def start(self):
        """Start the network manager"""
        self._session = aiohttp.ClientSession()
        self.discovery.start()
        logger.info("Network manager started")
    
    async def stop(self):
        """Stop the network manager"""
        await self.disconnect()
        self.discovery.stop()
        if self._session:
            await self._session.close()
        logger.info("Network manager stopped")
    
    def on_connected(self, callback: Callable):
        """Register callback for connection established"""
        self._on_connected_callbacks.append(callback)
    
    def on_disconnected(self, callback: Callable):
        """Register callback for connection lost"""
        self._on_disconnected_callbacks.append(callback)
    
    def on_message(self, callback: Callable):
        """Register callback for incoming messages"""
        self._on_message_callbacks.append(callback)
    
    def register_handler(self, msg_type: str, handler: Callable):
        """Register handler for specific message type"""
        self._message_handlers[msg_type] = handler
    
    async def connect(self, host: str, port: int = 8765) -> bool:
        """Connect to server"""
        if self._connecting or self._connected:
            return True
        
        self._connecting = True
        self.server_host = host
        self.server_port = port
        
        try:
            url = f"ws://{host}:{port}/ws"
            logger.info(f"Connecting to {url}")
            
            self._ws = await self._session.ws_connect(url, heartbeat=30)
            self._connected = True
            self._connecting = False
            
            logger.info("Connected to server")
            
            # Start heartbeat
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            
            # Start message receiver
            asyncio.create_task(self._receive_messages())
            
            # Notify callbacks
            for callback in self._on_connected_callbacks:
                try:
                    callback()
                except Exception as e:
                    logger.error(f"Error in connected callback: {e}")
            
            # Process offline queue
            await self._process_offline_queue()
            
            return True
            
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            self._connecting = False
            self._connected = False
            return False
    
    async def disconnect(self):
        """Disconnect from server"""
        self._connected = False
        self._connecting = False
        
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        
        if self._reconnect_task:
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass
        
        if self._ws:
            await self._ws.close()
            self._ws = None
        
        logger.info("Disconnected from server")
        
        # Notify callbacks
        for callback in self._on_disconnected_callbacks:
            try:
                callback()
            except Exception as e:
                logger.error(f"Error in disconnected callback: {e}")
    
    async def _receive_messages(self):
        """Receive and process messages from server"""
        try:
            async for msg in self._ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    await self._process_message(msg.data)
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error(f"WebSocket error: {self._ws.exception()}")
                    break
                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    break
        except Exception as e:
            logger.error(f"Error receiving messages: {e}")
        finally:
            if self._connected:
                await self._handle_disconnect()
    
    async def _process_message(self, data: str):
        """Process incoming message"""
        try:
            msg = ProtocolMessage.from_json(data)
            
            # Call registered handlers
            if msg.type in self._message_handlers:
                handler = self._message_handlers[msg.type]
                await handler(msg)
            
            # Fulfill pending requests
            if msg.payload.get('request_id') in self._pending_requests:
                future = self._pending_requests.pop(msg.payload['request_id'])
                if not future.done():
                    future.set_result(msg)
            
            # Call general message callbacks
            for callback in self._on_message_callbacks:
                try:
                    callback(msg)
                except Exception as e:
                    logger.error(f"Error in message callback: {e}")
                    
        except Exception as e:
            logger.error(f"Error processing message: {e}")
    
    async def _handle_disconnect(self):
        """Handle unexpected disconnection"""
        self._connected = False
        
        # Notify callbacks
        for callback in self._on_disconnected_callbacks:
            try:
                callback()
            except Exception as e:
                logger.error(f"Error in disconnected callback: {e}")
        
        # Try to reconnect
        if self.server_host:
            self._reconnect_task = asyncio.create_task(self._reconnect_loop())
    
    async def _reconnect_loop(self):
        """Attempt to reconnect with exponential backoff"""
        delay = 1
        max_delay = 60
        
        while not self._connected:
            try:
                await asyncio.sleep(delay)
                logger.info(f"Attempting to reconnect (delay: {delay}s)")
                
                if await self.connect(self.server_host, self.server_port):
                    logger.info("Reconnected successfully")
                    return
                
                delay = min(delay * 2, max_delay)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Reconnection attempt failed: {e}")
                delay = min(delay * 2, max_delay)
    
    async def _heartbeat_loop(self):
        """Send periodic heartbeats"""
        while self._connected:
            try:
                await asyncio.sleep(30)
                if self._connected and self._ws:
                    msg = create_message(
                        MessageType.HEARTBEAT,
                        {'timestamp': time.time()},
                        token=self.session_token
                    )
                    await self._ws.send_str(msg.to_json())
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
                break
    
    async def _process_offline_queue(self):
        """Process messages queued while offline"""
        while self._message_queue and self._connected:
            msg = self._message_queue.pop(0)
            try:
                await self._send_message(msg)
            except Exception as e:
                logger.error(f"Error sending queued message: {e}")
                # Put back at front if failed
                self._message_queue.insert(0, msg)
                break
    
    async def _send_message(self, msg: ProtocolMessage, wait_response: bool = False) -> Optional[ProtocolMessage]:
        """Send message to server"""
        if not self._connected or not self._ws:
            # Queue for later
            self._message_queue.append(msg)
            if wait_response:
                return None
            return
        
        try:
            await self._ws.send_str(msg.to_json())
            
            if wait_response:
                future = asyncio.get_event_loop().create_future()
                request_id = str(uuid.uuid4())
                msg.payload['request_id'] = request_id
                self._pending_requests[request_id] = future
                
                try:
                    return await asyncio.wait_for(future, timeout=10)
                except asyncio.TimeoutError:
                    self._pending_requests.pop(request_id, None)
                    return None
                    
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            if not self._connected:
                self._message_queue.append(msg)
    
    async def send(self, msg: ProtocolMessage) -> bool:
        """Send message without waiting for response"""
        await self._send_message(msg)
        return True
    
    async def send_request(self, msg: ProtocolMessage) -> Optional[ProtocolMessage]:
        """Send message and wait for response"""
        return await self._send_message(msg, wait_response=True)
    
    async def register(self, username: str, password: str, display_name: str = None) -> Dict:
        """Register new user"""
        msg = create_message(
            MessageType.AUTH_REGISTER,
            {
                'username': username,
                'password': password,
                'display_name': display_name or username
            }
        )
        response = await self.send_request(msg)
        if response:
            return response.payload
        return {'success': False, 'error': 'No response from server'}
    
    async def login(self, username: str, password: str, device_id: str = None) -> Dict:
        """Login to server"""
        msg = create_message(
            MessageType.AUTH_LOGIN,
            {
                'username': username,
                'password': password,
                'device_id': device_id,
                'device_name': 'Desktop Client'
            }
        )
        response = await self.send_request(msg)
        if response and response.payload.get('success'):
            self.session_token = response.payload.get('token')
            self.user_id = response.payload.get('user_id')
            self.username = response.payload.get('username')
        return response.payload if response else {'success': False, 'error': 'No response'}
    
    async def logout(self):
        """Logout from server"""
        msg = create_message(
            MessageType.AUTH_LOGOUT,
            {},
            token=self.session_token
        )
        await self.send(msg)
        self.session_token = None
        self.user_id = None
        self.username = None
    
    async def send_message(self, chat_id: str, content: str, content_type: str = 'text',
                          reply_to: str = None) -> bool:
        """Send chat message"""
        msg = create_message(
            MessageType.MESSAGE_SEND,
            {
                'chat_id': chat_id,
                'content': content,
                'content_type': content_type,
                'reply_to': reply_to
            },
            token=self.session_token,
            sender=self.user_id
        )
        return await self.send(msg)
    
    async def get_message_history(self, chat_id: str, limit: int = 50, 
                                  before: float = None) -> Dict:
        """Get message history for a chat"""
        payload = {'chat_id': chat_id, 'limit': limit}
        if before:
            payload['before'] = before
        
        msg = create_message(
            MessageType.MESSAGE_HISTORY,
            payload,
            token=self.session_token,
            sender=self.user_id
        )
        response = await self.send_request(msg)
        return response.payload if response else {}
    
    async def create_chat(self, chat_type: str = 'private', name: str = None,
                         members: List[str] = None) -> Dict:
        """Create a new chat"""
        if members is None:
            members = [self.user_id]
        
        msg = create_message(
            MessageType.CHAT_CREATE,
            {
                'type': chat_type,
                'name': name,
                'members': members
            },
            token=self.session_token,
            sender=self.user_id
        )
        response = await self.send_request(msg)
        return response.payload if response else {}
    
    async def get_chat_list(self) -> Dict:
        """Get user's chat list"""
        msg = create_message(
            MessageType.CHAT_LIST,
            {},
            token=self.session_token,
            sender=self.user_id
        )
        response = await self.send_request(msg)
        return response.payload if response else {}
    
    async def get_user_list(self) -> Dict:
        """Get list of all users"""
        msg = create_message(
            MessageType.USER_LIST,
            {},
            token=self.session_token,
            sender=self.user_id
        )
        response = await self.send_request(msg)
        return response.payload if response else {}
    
    async def send_typing(self, chat_id: str, is_typing: bool = True):
        """Send typing indicator"""
        msg_type = MessageType.TYPING_START if is_typing else MessageType.TYPING_STOP
        msg = create_message(
            msg_type,
            {'chat_id': chat_id},
            token=self.session_token,
            sender=self.user_id
        )
        await self.send(msg)
    
    async def mark_read(self, message_id: str):
        """Mark message as read"""
        msg = create_message(
            MessageType.MESSAGE_READ,
            {'message_id': message_id},
            token=self.session_token,
            sender=self.user_id
        )
        await self.send(msg)
