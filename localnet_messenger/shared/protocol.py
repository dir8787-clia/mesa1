"""
LocalNet Messenger - Shared Protocol Module
Defines message types and protocol structure
"""

from enum import Enum
from typing import Dict, Any, Optional
import json
import time
import uuid


class MessageType(Enum):
    """Protocol message types"""
    # Authentication
    AUTH_REGISTER = "auth.register"
    AUTH_LOGIN = "auth.login"
    AUTH_LOGOUT = "auth.logout"
    AUTH_TOKEN_REFRESH = "auth.token_refresh"
    
    # Presence
    PRESENCE_UPDATE = "presence.update"
    USER_LIST = "user.list"
    USER_STATUS = "user.status"
    
    # Chats
    CHAT_CREATE = "chat.create"
    CHAT_OPEN = "chat.open"
    CHAT_LIST = "chat.list"
    CHAT_DELETE = "chat.delete"
    
    # Messages
    MESSAGE_SEND = "message.send"
    MESSAGE_EDIT = "message.edit"
    MESSAGE_DELETE = "message.delete"
    MESSAGE_READ = "message.read"
    MESSAGE_DELIVERED = "message.delivered"
    TYPING_START = "typing.start"
    TYPING_STOP = "typing.stop"
    
    # Groups
    GROUP_CREATE = "group.create"
    GROUP_JOIN = "group.join"
    GROUP_LEAVE = "group.leave"
    GROUP_INVITE = "group.invite"
    GROUP_REMOVE = "group.remove"
    GROUP_UPDATE = "group.update"
    
    # Files
    FILE_UPLOAD_START = "file.upload.start"
    FILE_UPLOAD_CHUNK = "file.upload.chunk"
    FILE_UPLOAD_END = "file.upload.end"
    FILE_DOWNLOAD_REQUEST = "file.download.request"
    FILE_TRANSFER_PROGRESS = "file.transfer.progress"
    
    # System
    ERROR = "error"
    PING = "ping"
    PONG = "pong"


class ProtocolMessage:
    """Protocol message structure"""
    
    VERSION = "1.0"
    
    def __init__(
        self,
        msg_type: MessageType,
        payload: Dict[str, Any],
        msg_id: Optional[str] = None,
        sender: Optional[str] = None,
        recipient: Optional[str] = None,
        timestamp: Optional[float] = None,
        auth_token: Optional[str] = None,
        status: Optional[str] = None
    ):
        self.version = self.VERSION
        self.type = msg_type.value if isinstance(msg_type, MessageType) else msg_type
        self.id = msg_id or str(uuid.uuid4())
        self.timestamp = timestamp or time.time()
        self.sender = sender
        self.recipient = recipient
        self.payload = payload or {}
        self.auth_token = auth_token
        self.status = status
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        data = {
            "version": self.version,
            "type": self.type,
            "id": self.id,
            "timestamp": self.timestamp,
            "payload": self.payload
        }
        
        if self.sender:
            data["sender"] = self.sender
        if self.recipient:
            data["recipient"] = self.recipient
        if self.auth_token:
            data["auth_token"] = self.auth_token
        if self.status:
            data["status"] = self.status
            
        return data
    
    def to_json(self) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProtocolMessage":
        """Create from dictionary"""
        return cls(
            msg_type=data.get("type", ""),
            payload=data.get("payload", {}),
            msg_id=data.get("id"),
            sender=data.get("sender"),
            recipient=data.get("recipient"),
            timestamp=data.get("timestamp"),
            auth_token=data.get("auth_token"),
            status=data.get("status")
        )
    
    @classmethod
    def from_json(cls, json_str: str) -> "ProtocolMessage":
        """Create from JSON string"""
        return cls.from_dict(json.loads(json_str))
    
    @staticmethod
    def create_ping() -> "ProtocolMessage":
        """Create a ping message"""
        return ProtocolMessage(MessageType.PING, {})
    
    @staticmethod
    def create_pong(msg_id: str) -> "ProtocolMessage":
        """Create a pong message in response to ping"""
        return ProtocolMessage(MessageType.PONG, {"ping_id": msg_id})
    
    @staticmethod
    def create_error(error_msg: str, error_code: str = "UNKNOWN_ERROR", original_msg_id: Optional[str] = None) -> "ProtocolMessage":
        """Create an error message"""
        payload = {"error": error_msg, "code": error_code}
        if original_msg_id:
            payload["original_id"] = original_msg_id
        return ProtocolMessage(MessageType.ERROR, payload)
