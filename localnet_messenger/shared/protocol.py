#!/usr/bin/env python3
"""
LocalNet Messenger - Shared Protocol Module
Defines message types and protocol message structure
"""
import json
import time
import uuid
from enum import Enum
from typing import Optional, Dict, Any


class MessageType(Enum):
    """Protocol message types"""
    # Authentication
    AUTH_REGISTER = "auth.register"
    AUTH_LOGIN = "auth.login"
    AUTH_LOGOUT = "auth.logout"
    
    # Presence
    PRESENCE_UPDATE = "presence.update"
    PRESENCE_STATUS = "presence.status"
    
    # Users
    USER_LIST = "user.list"
    USER_INFO = "user.info"
    
    # Chats
    CHAT_CREATE = "chat.create"
    CHAT_OPEN = "chat.open"
    CHAT_LIST = "chat.list"
    CHAT_LEAVE = "chat.leave"
    
    # Messages
    MESSAGE_SEND = "message.send"
    MESSAGE_EDIT = "message.edit"
    MESSAGE_DELETE = "message.delete"
    MESSAGE_READ = "message.read"
    MESSAGE_HISTORY = "message.history"
    MESSAGE_DELIVERED = "message.delivered"
    
    # Typing indicators
    TYPING_START = "typing.start"
    TYPING_STOP = "typing.stop"
    
    # Groups
    GROUP_CREATE = "group.create"
    GROUP_JOIN = "group.join"
    GROUP_LEAVE = "group.leave"
    GROUP_INVITE = "group.invite"
    GROUP_UPDATE = "group.update"
    
    # Files
    FILE_UPLOAD_START = "file.upload.start"
    FILE_UPLOAD_CHUNK = "file.upload.chunk"
    FILE_UPLOAD_END = "file.upload.end"
    FILE_DOWNLOAD_REQUEST = "file.download.request"
    FILE_INFO = "file.info"
    
    # System
    HEARTBEAT = "heartbeat"
    ERROR = "error"
    SUCCESS = "success"


class ProtocolMessage:
    """Represents a protocol message"""
    
    def __init__(self, msg_type: MessageType, payload: Dict[str, Any],
                 sender: str = "", token: str = "", msg_id: str = None,
                 timestamp: float = None):
        self.version = "1.0"
        self.type = msg_type.value if isinstance(msg_type, MessageType) else msg_type
        self.id = msg_id or str(uuid.uuid4())
        self.timestamp = timestamp or time.time()
        self.sender = sender
        self.token = token
        self.payload = payload
    
    def to_json(self) -> str:
        """Convert message to JSON string"""
        data = {
            'version': self.version,
            'type': self.type,
            'id': self.id,
            'timestamp': self.timestamp,
            'sender': self.sender,
            'payload': self.payload
        }
        if self.token:
            data['token'] = self.token
        return json.dumps(data)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'ProtocolMessage':
        """Create message from JSON string"""
        data = json.loads(json_str)
        msg = cls(
            msg_type=data.get('type', ''),
            payload=data.get('payload', {}),
            sender=data.get('sender', ''),
            token=data.get('token', ''),
            msg_id=data.get('id'),
            timestamp=data.get('timestamp')
        )
        msg.version = data.get('version', '1.0')
        return msg
    
    def __repr__(self) -> str:
        return f"ProtocolMessage(type={self.type}, id={self.id})"


def create_message(msg_type: MessageType, payload: Dict[str, Any],
                   sender: str = "", token: str = "") -> ProtocolMessage:
    """Helper function to create a protocol message"""
    return ProtocolMessage(
        msg_type=msg_type,
        payload=payload,
        sender=sender,
        token=token
    )
