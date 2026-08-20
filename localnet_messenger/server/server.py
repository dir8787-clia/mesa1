"""
LocalNet Messenger Server
Main server entry point with WebSocket support and mDNS discovery
"""
import asyncio
import json
import signal
import sys
from pathlib import Path
from typing import Optional
import logging

import aiohttp
from aiohttp import web
from zeroconf import ServiceInfo, Zeroconf

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from server.database import Database
from server.handlers.websocket_handler import ConnectionManager, MessageHandler

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class LocalNetServer:
    def __init__(self, host: str = '0.0.0.0', port: int = 8765, 
                 data_dir: Optional[str] = None):
        self.host = host
        self.port = port
        self.data_dir = Path(data_dir) if data_dir else Path(__file__).parent / 'data'
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.db: Optional[Database] = None
        self.conn_manager = ConnectionManager()
        self.handler: Optional[MessageHandler] = None
        self.app: Optional[web.Application] = None
        self.runner: Optional[web.AppRunner] = None
        self.zeroconf: Optional[Zeroconf] = None
        self.service_info: Optional[ServiceInfo] = None
        
        self._shutdown_event = asyncio.Event()
    
    async def start(self):
        """Start the server"""
        logger.info(f"Starting LocalNet Messenger Server on {self.host}:{self.port}")
        
        # Initialize database
        db_path = self.data_dir / 'messenger.db'
        self.db = Database(str(db_path))
        await self.db.connect()
        logger.info(f"Database initialized at {db_path}")
        
        # Initialize message handler
        self.handler = MessageHandler(self.db, self.conn_manager)
        
        # Create web application
        self.app = web.Application()
        self.app.router.add_get('/ws', self.websocket_handler)
        self.app.router.add_get('/health', self.health_check)
        
        # Start web server
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, self.host, self.port)
        await site.start()
        logger.info(f"WebSocket server started at ws://{self.host}:{self.port}/ws")
        
        # Start mDNS service discovery
        await self.start_mdns()
        
        logger.info("Server is ready to accept connections")
        
        # Wait for shutdown signal
        await self._shutdown_event.wait()
    
    async def stop(self):
        """Stop the server"""
        logger.info("Shutting down server...")
        
        # Stop mDNS
        if self.zeroconf:
            try:
                if self.service_info:
                    self.zeroconf.unregister_service(self.service_info)
                self.zeroconf.close()
            except Exception as e:
                logger.error(f"Error stopping mDNS: {e}")
        
        # Close all connections
        for user_id in list(self.conn_manager.connections.keys()):
            await self.db.update_user_status(user_id, 'offline')
        
        # Stop web server
        if self.runner:
            await self.runner.cleanup()
        
        # Close database
        if self.db:
            await self.db.close()
        
        logger.info("Server stopped")
    
    async def websocket_handler(self, request: web.Request):
        """Handle WebSocket connections"""
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        
        logger.info(f"New WebSocket connection from {request.remote}")
        
        try:
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    await self.handler.handle_message(ws, msg.data)
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error(f"WebSocket error: {ws.exception()}")
                    break
        finally:
            # Handle disconnect
            user_id = self.conn_manager.get_user_id(ws)
            if user_id:
                await self.db.update_user_status(user_id, 'offline')
                self.conn_manager.remove_connection(ws)
                
                # Broadcast offline status
                await self.conn_manager.broadcast(
                    self.handler.create_message(
                        'presence.status',
                        {'user_id': user_id, 'status': 'offline'},
                        sender='server'
                    ),
                    exclude_user=user_id
                )
            
            logger.info(f"WebSocket connection closed: {request.remote}")
        
        return ws
    
    async def health_check(self, request: web.Request):
        """Health check endpoint"""
        return web.json_response({
            'status': 'ok',
            'connections': len(self.conn_manager.user_ids),
            'users': len(self.conn_manager.connections)
        })
    
    async def start_mdns(self):
        """Start mDNS service discovery"""
        try:
            self.zeroconf = Zeroconf()
            
            # Get local IP
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                s.connect(('8.8.8.8', 80))
                local_ip = s.getsockname()[0]
            finally:
                s.close()
            
            self.service_info = ServiceInfo(
                "_localnet-messenger._tcp.local.",
                f"LocalNet Messenger._localnet-messenger._tcp.local.",
                addresses=[socket.inet_aton(local_ip)],
                port=self.port,
                properties={
                    'version': '1.0',
                    'path': '/ws'
                },
                server=f"{local_ip}.local."
            )
            
            self.zeroconf.register_service(self.service_info)
            logger.info(f"mDNS service registered: _localnet-messenger._tcp.local. at {local_ip}:{self.port}")
            
        except Exception as e:
            logger.warning(f"Could not start mDNS service: {e}")
            logger.warning("Clients will need to connect manually by IP address")
    
    def create_message(self, msg_type: str, payload: dict, sender: str = 'server'):
        """Helper to create protocol messages"""
        import time
        import uuid
        return type('ProtocolMessage', (), {
            'to_json': lambda self: json.dumps({
                'version': '1.0',
                'type': msg_type,
                'id': str(uuid.uuid4()),
                'timestamp': time.time(),
                'sender': sender,
                'payload': payload
            })
        })()


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='LocalNet Messenger Server')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to')
    parser.add_argument('--port', type=int, default=8765, help='Port to listen on')
    parser.add_argument('--data-dir', help='Directory for data storage')
    
    args = parser.parse_args()
    
    server = LocalNetServer(host=args.host, port=args.port, data_dir=args.data_dir)
    
    # Setup signal handlers
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    def signal_handler():
        logger.info("Received shutdown signal")
        loop.create_task(server.stop())
        server._shutdown_event.set()
    
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)
    
    try:
        loop.run_until_complete(server.start())
    except KeyboardInterrupt:
        pass
    finally:
        loop.close()


if __name__ == '__main__':
    main()
