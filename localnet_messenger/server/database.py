"""LocalNet Messenger - Server Database Module"""
import aiosqlite
import json
from pathlib import Path
from typing import Optional, List, Dict, Any
import logging

logger = logging.getLogger(__name__)


class Database:
    """SQLite database manager for the server"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None
    
    async def connect(self):
        """Connect to database and initialize schema"""
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._init_schema()
    
    async def close(self):
        """Close database connection"""
        if self._conn:
            await self._conn.close()
    
    async def _init_schema(self):
        """Initialize database schema"""
        await self._conn.executescript('''
            -- Users table
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                display_name TEXT,
                avatar BLOB,
                status TEXT DEFAULT 'offline',
                created_at REAL DEFAULT (strftime('%s', 'now')),
                last_seen REAL
            );
            
            -- Sessions table
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                device_id TEXT,
                device_name TEXT,
                token TEXT UNIQUE NOT NULL,
                created_at REAL DEFAULT (strftime('%s', 'now')),
                expires_at REAL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            
            -- Chats table
            CREATE TABLE IF NOT EXISTS chats (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL CHECK(type IN ('private', 'group')),
                name TEXT,
                avatar BLOB,
                created_by TEXT,
                created_at REAL DEFAULT (strftime('%s', 'now')),
                FOREIGN KEY (created_by) REFERENCES users(id)
            );
            
            -- Chat members table
            CREATE TABLE IF NOT EXISTS chat_members (
                chat_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                role TEXT DEFAULT 'member' CHECK(role IN ('owner', 'admin', 'member')),
                joined_at REAL DEFAULT (strftime('%s', 'now')),
                PRIMARY KEY (chat_id, user_id),
                FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            
            -- Messages table
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                chat_id TEXT NOT NULL,
                sender_id TEXT NOT NULL,
                content TEXT NOT NULL,
                content_type TEXT DEFAULT 'text',
                reply_to TEXT,
                edited_at REAL,
                deleted INTEGER DEFAULT 0,
                created_at REAL DEFAULT (strftime('%s', 'now')),
                FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE,
                FOREIGN KEY (sender_id) REFERENCES users(id)
            );
            
            -- Read receipts table
            CREATE TABLE IF NOT EXISTS read_receipts (
                message_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                read_at REAL DEFAULT (strftime('%s', 'now')),
                PRIMARY KEY (message_id, user_id),
                FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            
            -- Files table
            CREATE TABLE IF NOT EXISTS files (
                id TEXT PRIMARY KEY,
                message_id TEXT,
                filename TEXT NOT NULL,
                filepath TEXT NOT NULL,
                size INTEGER,
                mime_type TEXT,
                uploaded_at REAL DEFAULT (strftime('%s', 'now')),
                FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE SET NULL
            );
            
            -- Contacts table
            CREATE TABLE IF NOT EXISTS contacts (
                user_id TEXT NOT NULL,
                contact_id TEXT NOT NULL,
                blocked INTEGER DEFAULT 0,
                added_at REAL DEFAULT (strftime('%s', 'now')),
                PRIMARY KEY (user_id, contact_id),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (contact_id) REFERENCES users(id) ON DELETE CASCADE
            );
            
            -- Create indexes
            CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_id);
            CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages(sender_id);
            CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_at);
            CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
            CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(token);
            CREATE INDEX IF NOT EXISTS idx_chat_members_user ON chat_members(user_id);
        ''')
        await self._conn.commit()
        logger.info("Database schema initialized")
    
    # User operations
    async def create_user(self, user_id: str, username: str, password_hash: str, 
                         display_name: str = None) -> bool:
        """Create a new user"""
        try:
            await self._conn.execute(
                '''INSERT INTO users (id, username, password_hash, display_name)
                   VALUES (?, ?, ?, ?)''',
                (user_id, username, password_hash, display_name or username)
            )
            await self._conn.commit()
            return True
        except aiosqlite.IntegrityError:
            return False
    
    async def get_user_by_username(self, username: str) -> Optional[Dict]:
        """Get user by username"""
        cursor = await self._conn.execute(
            'SELECT * FROM users WHERE username = ?', (username,)
        )
        row = await cursor.fetchone()
        if row:
            return dict(row)
        return None
    
    async def get_user_by_id(self, user_id: str) -> Optional[Dict]:
        """Get user by ID"""
        cursor = await self._conn.execute(
            'SELECT * FROM users WHERE id = ?', (user_id,)
        )
        row = await cursor.fetchone()
        if row:
            return dict(row)
        return None
    
    async def update_user_status(self, user_id: str, status: str):
        """Update user online status"""
        await self._conn.execute(
            '''UPDATE users SET status = ?, last_seen = strftime('%s', 'now')
               WHERE id = ?''',
            (status, user_id)
        )
        await self._conn.commit()
    
    async def get_all_users(self) -> List[Dict]:
        """Get all users"""
        cursor = await self._conn.execute('SELECT id, username, display_name, status FROM users')
        return [dict(row) for row in await cursor.fetchall()]
    
    # Session operations
    async def create_session(self, session_id: str, user_id: str, device_id: str,
                            device_name: str, token: str, expires_at: float = None) -> bool:
        """Create a new session"""
        await self._conn.execute(
            '''INSERT INTO sessions (id, user_id, device_id, device_name, token, expires_at)
               VALUES (?, ?, ?, ?, ?, ?)''',
            (session_id, user_id, device_id, device_name, token, expires_at)
        )
        await self._conn.commit()
        return True
    
    async def get_session_by_token(self, token: str) -> Optional[Dict]:
        """Get session by token"""
        cursor = await self._conn.execute(
            'SELECT * FROM sessions WHERE token = ?', (token,)
        )
        row = await cursor.fetchone()
        if row:
            return dict(row)
        return None
    
    async def delete_session(self, token: str):
        """Delete a session"""
        await self._conn.execute('DELETE FROM sessions WHERE token = ?', (token,))
        await self._conn.commit()
    
    # Chat operations
    async def create_chat(self, chat_id: str, chat_type: str, name: str = None,
                         created_by: str = None) -> bool:
        """Create a new chat"""
        await self._conn.execute(
            '''INSERT INTO chats (id, type, name, created_by)
               VALUES (?, ?, ?, ?)''',
            (chat_id, chat_type, name, created_by)
        )
        await self._conn.commit()
        return True
    
    async def add_chat_member(self, chat_id: str, user_id: str, role: str = 'member'):
        """Add member to chat"""
        await self._conn.execute(
            '''INSERT OR REPLACE INTO chat_members (chat_id, user_id, role)
               VALUES (?, ?, ?)''',
            (chat_id, user_id, role)
        )
        await self._conn.commit()
    
    async def remove_chat_member(self, chat_id: str, user_id: str):
        """Remove member from chat"""
        await self._conn.execute(
            'DELETE FROM chat_members WHERE chat_id = ? AND user_id = ?',
            (chat_id, user_id)
        )
        await self._conn.commit()
    
    async def get_chat_members(self, chat_id: str) -> List[Dict]:
        """Get chat members"""
        cursor = await self._conn.execute(
            '''SELECT u.id, u.username, u.display_name, u.status, cm.role
               FROM chat_members cm
               JOIN users u ON cm.user_id = u.id
               WHERE cm.chat_id = ?''',
            (chat_id,)
        )
        return [dict(row) for row in await cursor.fetchall()]
    
    async def get_user_chats(self, user_id: str) -> List[Dict]:
        """Get all chats for a user"""
        cursor = await self._conn.execute(
            '''SELECT c.* FROM chats c
               JOIN chat_members cm ON c.id = cm.chat_id
               WHERE cm.user_id = ?''',
            (user_id,)
        )
        return [dict(row) for row in await cursor.fetchall()]
    
    async def get_chat(self, chat_id: str) -> Optional[Dict]:
        """Get chat by ID"""
        cursor = await self._conn.execute(
            'SELECT * FROM chats WHERE id = ?', (chat_id,)
        )
        row = await cursor.fetchone()
        if row:
            return dict(row)
        return None
    
    # Message operations
    async def create_message(self, msg_id: str, chat_id: str, sender_id: str,
                            content: str, content_type: str = 'text',
                            reply_to: str = None) -> bool:
        """Create a new message"""
        await self._conn.execute(
            '''INSERT INTO messages (id, chat_id, sender_id, content, content_type, reply_to)
               VALUES (?, ?, ?, ?, ?, ?)''',
            (msg_id, chat_id, sender_id, content, content_type, reply_to)
        )
        await self._conn.commit()
        return True
    
    async def get_message_history(self, chat_id: str, limit: int = 50,
                                  before: float = None) -> List[Dict]:
        """Get message history for a chat"""
        if before:
            cursor = await self._conn.execute(
                '''SELECT m.*, u.username as sender_username, u.display_name as sender_display_name
                   FROM messages m
                   JOIN users u ON m.sender_id = u.id
                   WHERE m.chat_id = ? AND m.created_at < ? AND m.deleted = 0
                   ORDER BY m.created_at DESC
                   LIMIT ?''',
                (chat_id, before, limit)
            )
        else:
            cursor = await self._conn.execute(
                '''SELECT m.*, u.username as sender_username, u.display_name as sender_display_name
                   FROM messages m
                   JOIN users u ON m.sender_id = u.id
                   WHERE m.chat_id = ? AND m.deleted = 0
                   ORDER BY m.created_at DESC
                   LIMIT ?''',
                (chat_id, limit)
            )
        return [dict(row) for row in await cursor.fetchall()]
    
    async def edit_message(self, msg_id: str, content: str, user_id: str) -> bool:
        """Edit a message"""
        cursor = await self._conn.execute(
            '''UPDATE messages SET content = ?, edited_at = strftime('%s', 'now')
               WHERE id = ? AND sender_id = ?''',
            (content, msg_id, user_id)
        )
        await self._conn.commit()
        return cursor.rowcount > 0
    
    async def delete_message(self, msg_id: str, user_id: str) -> bool:
        """Delete a message (soft delete)"""
        cursor = await self._conn.execute(
            '''UPDATE messages SET deleted = 1
               WHERE id = ? AND sender_id = ?''',
            (msg_id, user_id)
        )
        await self._conn.commit()
        return cursor.rowcount > 0
    
    async def mark_message_read(self, msg_id: str, user_id: str):
        """Mark message as read"""
        await self._conn.execute(
            '''INSERT OR IGNORE INTO read_receipts (message_id, user_id)
               VALUES (?, ?)''',
            (msg_id, user_id)
        )
        await self._conn.commit()
    
    async def get_unread_messages(self, chat_id: str, user_id: str) -> List[Dict]:
        """Get unread messages for a user in a chat"""
        cursor = await self._conn.execute(
            '''SELECT m.* FROM messages m
               LEFT JOIN read_receipts rr ON m.id = rr.message_id AND rr.user_id = ?
               WHERE m.chat_id = ? AND m.sender_id != ? AND rr.message_id IS NULL
               AND m.deleted = 0''',
            (user_id, chat_id, user_id)
        )
        return [dict(row) for row in await cursor.fetchall()]
    
    # Contact operations
    async def add_contact(self, user_id: str, contact_id: str):
        """Add a contact"""
        await self._conn.execute(
            '''INSERT OR IGNORE INTO contacts (user_id, contact_id)
               VALUES (?, ?)''',
            (user_id, contact_id)
        )
        await self._conn.commit()
    
    async def block_contact(self, user_id: str, contact_id: str):
        """Block a contact"""
        await self._conn.execute(
            '''INSERT OR REPLACE INTO contacts (user_id, contact_id, blocked)
               VALUES (?, ?, 1)''',
            (user_id, contact_id)
        )
        await self._conn.commit()
    
    async def get_contacts(self, user_id: str) -> List[Dict]:
        """Get user's contacts"""
        cursor = await self._conn.execute(
            '''SELECT u.id, u.username, u.display_name, u.status, c.blocked
               FROM contacts c
               JOIN users u ON c.contact_id = u.id
               WHERE c.user_id = ?''',
            (user_id,)
        )
        return [dict(row) for row in await cursor.fetchall()]
    
    # File operations
    async def save_file_info(self, file_id: str, message_id: str, filename: str,
                            filepath: str, size: int, mime_type: str = None):
        """Save file information"""
        await self._conn.execute(
            '''INSERT INTO files (id, message_id, filename, filepath, size, mime_type)
               VALUES (?, ?, ?, ?, ?, ?)''',
            (file_id, message_id, filename, filepath, size, mime_type)
        )
        await self._conn.commit()
