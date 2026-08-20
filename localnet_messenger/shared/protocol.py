"""
LocalNet Messenger Protocol Definition
JSON-based protocol over WebSocket/TCP
"""
import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Optional, Dict, List
from enum import Enum


class MessageType(Enum):
    # Authentication
    AUTH_REGISTER = "auth.register"
    AUTH_LOGIN = "auth.login"
    AUTH_LOGOUT = "auth.logout"
    AUTH_TOKEN_REFRESH = "auth.token_refresh"
    
    # Presence
    PRESENCE_UPDATE = "presence.update"
    PRESENCE_STATUS = "presence.status"
    
    # Users
    USER_LIST = "user.list"
    USER_INFO = "user.info"
    USER_PROFILE_UPDATE = "user.profile_update"
    
    # Contacts
    CONTACT_ADD = "contact.add"
    CONTACT_REMOVE = "contact.remove"
    CONTACT_BLOCK = "contact.block"
    CONTACT_LIST = "contact.list"
    
    # Chats
    CHAT_CREATE = "chat.create"
    CHAT_OPEN = "chat.open"
    CHAT_CLOSE = "chat.close"
    CHAT_LIST = "chat.list"
    CHAT_DELETE = "chat.delete"
    
    # Messages
    MESSAGE_SEND = "message.send"
    MESSAGE_EDIT = "message.edit"
    MESSAGE_DELETE = "message.delete"
    MESSAGE_READ = "message.read"
    MESSAGE_RECEIVED = "message.received"
    MESSAGE_HISTORY = "message.history"
    
    # Typing indicators
    TYPING_START = "typing.start"
    TYPING_STOP = "typing.stop"
    
    # Files
    FILE_UPLOAD_START = "file.upload.start"
    FILE_UPLOAD_CHUNK = "file.upload.chunk"
    FILE_UPLOAD_END = "file.upload.end"
    FILE_DOWNLOAD_REQUEST = "file.download.request"
    FILE_DOWNLOAD_CHUNK = "file.download.chunk"
    FILE_INFO = "file.info"
    
    # Groups
    GROUP_CREATE = "group.create"
    GROUP_JOIN = "group.join"
    GROUP_LEAVE = "group.leave"
    GROUP_INVITE = "group.invite"
    GROUP_REMOVE_MEMBER = "group.remove_member"
    GROUP_UPDATE = "group.update"
    GROUP_INFO = "group.info"
    
    # System
    HEARTBEAT = "heartbeat"
    HEARTBEAT_ACK = "heartbeat.ack"
    ERROR = "error"
    ACK = "ack"


class MessageStatus(Enum):
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"


@dataclass
class ProtocolMessage:
    """Base protocol message structure"""
    version: str = "1.0"
    type: str = ""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    sender: Optional[str] = None
    recipient: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)
    token: Optional[str] = None
    
    def to_json(self) -> str:
        return json.dumps(asdict(self))
    
    @classmethod
    def from_json(cls, data: str) -> 'ProtocolMessage':
        d = json.loads(data)
        return cls(**d)
    
    def create_response(self, msg_type: str, payload: Dict[str, Any] = None) -> 'ProtocolMessage':
        return ProtocolMessage(
            version=self.version,
            type=msg_type,
            id=str(uuid.uuid4()),
            timestamp=time.time(),
            sender=self.recipient,
            recipient=self.sender,
            payload=payload or {},
            token=None
        )


# Specific message payloads
@dataclass
class AuthRegisterPayload:
    username: str
    password: str
    display_name: Optional[str] = None


@dataclass
class AuthLoginPayload:
    username: str
    password: str
    device_id: Optional[str] = None


@dataclass
class AuthResponsePayload:
    success: bool
    token: Optional[str] = None
    user_id: Optional[str] = None
    username: Optional[str] = None
    error: Optional[str] = None


@dataclass
class MessageSendPayload:
    chat_id: str
    content: str
    content_type: str = "text"  # text, image, file
    reply_to: Optional[str] = None
    attachments: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ChatInfo:
    id: str
    name: str
    type: str  # private, group
    members: List[str] = field(default_factory=list)
    last_message: Optional[Dict] = None
    unread_count: int = 0
    created_at: float = 0
    avatar: Optional[str] = None


@dataclass
class UserInfo:
    id: str
    username: str
    display_name: str
    status: str = "offline"  # online, away, offline
    avatar: Optional[str] = None
    last_seen: float = 0


def create_message(msg_type: MessageType, payload: Dict[str, Any], 
                   token: Optional[str] = None, sender: Optional[str] = None,
                   recipient: Optional[str] = None) -> ProtocolMessage:
    """Helper to create protocol messages"""
    return ProtocolMessage(
        version="1.0",
        type=msg_type.value,
        id=str(uuid.uuid4()),
        timestamp=time.time(),
        sender=sender,
        recipient=recipient,
        payload=payload,
        token=token
    )
