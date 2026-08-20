"""
LocalNet Messenger Server Database Module
Handles all database operations using SQLite
"""
import aiosqlite
import asyncio
from pathlib import Path
from typing import Optional, List, Dict, Any
import time
import json


class Database:
    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self._db: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()
    
    async def connect(self):
        """Initialize database connection and create tables"""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(self.db_path))
        self._db.row_factory = aiosqlite.Row
        await self._create_tables()
    
    async def close(self):
        """Close database connection"""
        if self._db:
            await self._db.close()
    
    async def _create_tables(self):
        """Create all necessary tables"""
        async with self._db.cursor() as cursor:
            # Users table
            await cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    display_name TEXT,
                    avatar TEXT,
                    status TEXT DEFAULT 'offline',
                    last_seen REAL DEFAULT 0,
                    created_at REAL DEFAULT (strftime('%s', 'now')),
                    bio TEXT
                )
            ''')
            
            # Sessions/tokens table
            await cursor.execute('''
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    token TEXT UNIQUE NOT NULL,
                    device_id TEXT,
                    device_name TEXT,
                    created_at REAL DEFAULT (strftime('%s', 'now')),
                    expires_at REAL,
                    last_activity REAL DEFAULT (strftime('%s', 'now')),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            ''')
            
            # Contacts table
            await cursor.execute('''
                CREATE TABLE IF NOT EXISTS contacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    contact_id TEXT NOT NULL,
                    is_blocked INTEGER DEFAULT 0,
                    added_at REAL DEFAULT (strftime('%s', 'now')),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (contact_id) REFERENCES users(id) ON DELETE CASCADE,
                    UNIQUE(user_id, contact_id)
                )
            ''')
            
            # Chats table
            await cursor.execute('''
                CREATE TABLE IF NOT EXISTS chats (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    type TEXT NOT NULL,
                    avatar TEXT,
                    created_by TEXT NOT NULL,
                    created_at REAL DEFAULT (strftime('%s', 'now')),
                    updated_at REAL DEFAULT (strftime('%s', 'now')),
                    FOREIGN KEY (created_by) REFERENCES users(id)
                )
            ''')
            
            # Chat members table
            await cursor.execute('''
                CREATE TABLE IF NOT EXISTS chat_members (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    role TEXT DEFAULT 'member',
                    joined_at REAL DEFAULT (strftime('%s', 'now')),
                    notifications_enabled INTEGER DEFAULT 1,
                    FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    UNIQUE(chat_id, user_id)
                )
            ''')
            
            # Messages table
            await cursor.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    chat_id TEXT NOT NULL,
                    sender_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    content_type TEXT DEFAULT 'text',
                    reply_to TEXT,
                    edited INTEGER DEFAULT 0,
                    deleted INTEGER DEFAULT 0,
                    created_at REAL DEFAULT (strftime('%s', 'now')),
                    updated_at REAL DEFAULT (strftime('%s', 'now')),
                    FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE,
                    FOREIGN KEY (sender_id) REFERENCES users(id)
                )
            ''')
            
            # Read receipts table
            await cursor.execute('''
                CREATE TABLE IF NOT EXISTS read_receipts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    read_at REAL DEFAULT (strftime('%s', 'now')),
                    FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    UNIQUE(message_id, user_id)
                )
            ''')
            
            # Attachments/files table
            await cursor.execute('''
                CREATE TABLE IF NOT EXISTS attachments (
                    id TEXT PRIMARY KEY,
                    message_id TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    filepath TEXT NOT NULL,
                    filesize INTEGER NOT NULL,
                    mime_type TEXT,
                    uploaded_at REAL DEFAULT (strftime('%s', 'now')),
                    FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
                )
            ''')
            
            # Server settings table
            await cursor.execute('''
                CREATE TABLE IF NOT EXISTS server_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at REAL DEFAULT (strftime('%s', 'now'))
                )
            ''')
            
            # Create indexes for better performance
            await cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_id)')
            await cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages(sender_id)')
            await cursor.execute('CREATE INDEX IF NOT EXISTS idx_chat_members_user ON chat_members(user_id)')
            await cursor.execute('CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(token)')
            await cursor.execute('CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id)')
            
            # Insert default settings
            default_settings = [
                ('max_file_size', '104857600'),  # 100MB
                ('max_message_length', '4096'),
                ('session_timeout', '604800'),  # 7 days
                ('allow_registration', 'true'),
            ]
            for key, value in default_settings:
                await cursor.execute(
                    'INSERT OR IGNORE INTO server_settings (key, value) VALUES (?, ?)',
                    (key, value)
                )
            
            await self._db.commit()
    
    # User operations
    async def create_user(self, user_id: str, username: str, password_hash: str, 
                         display_name: Optional[str] = None) -> bool:
        """Create a new user"""
        async with self._lock:
            async with self._db.cursor() as cursor:
                try:
                    await cursor.execute(
                        '''INSERT INTO users (id, username, password_hash, display_name)
                           VALUES (?, ?, ?, ?)''',
                        (user_id, username, password_hash, display_name or username)
                    )
                    await self._db.commit()
                    return True
                except aiosqlite.IntegrityError:
                    return False
    
    async def get_user_by_username(self, username: str) -> Optional[Dict]:
        """Get user by username"""
        async with self._db.cursor() as cursor:
            await cursor.execute(
                'SELECT * FROM users WHERE username = ?', (username,)
            )
            row = await cursor.fetchone()
            if row:
                return dict(row)
            return None
    
    async def get_user_by_id(self, user_id: str) -> Optional[Dict]:
        """Get user by ID"""
        async with self._db.cursor() as cursor:
            await cursor.execute(
                'SELECT id, username, display_name, avatar, status, last_seen, bio FROM users WHERE id = ?',
                (user_id,)
            )
            row = await cursor.fetchone()
            if row:
                return dict(row)
            return None
    
    async def update_user_status(self, user_id: str, status: str):
        """Update user online status"""
        async with self._lock:
            async with self._db.cursor() as cursor:
                await cursor.execute(
                    'UPDATE users SET status = ?, last_seen = ? WHERE id = ?',
                    (status, time.time(), user_id)
                )
                await self._db.commit()
    
    async def update_user_profile(self, user_id: str, display_name: Optional[str] = None,
                                  avatar: Optional[str] = None, bio: Optional[str] = None):
        """Update user profile"""
        async with self._lock:
            updates = []
            params = []
            if display_name is not None:
                updates.append('display_name = ?')
                params.append(display_name)
            if avatar is not None:
                updates.append('avatar = ?')
                params.append(avatar)
            if bio is not None:
                updates.append('bio = ?')
                params.append(bio)
            
            if updates:
                params.append(user_id)
                async with self._db.cursor() as cursor:
                    await cursor.execute(
                        f'UPDATE users SET {", ".join(updates)} WHERE id = ?',
                        params
                    )
                    await self._db.commit()
    
    async def get_all_users(self) -> List[Dict]:
        """Get all users"""
        async with self._db.cursor() as cursor:
            await cursor.execute(
                'SELECT id, username, display_name, avatar, status, last_seen FROM users'
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    
    # Session operations
    async def create_session(self, session_id: str, user_id: str, token: str,
                            device_id: Optional[str] = None, device_name: Optional[str] = None,
                            expires_at: Optional[float] = None) -> bool:
        """Create a new session"""
        async with self._lock:
            async with self._db.cursor() as cursor:
                try:
                    await cursor.execute(
                        '''INSERT INTO sessions (id, user_id, token, device_id, device_name, expires_at)
                           VALUES (?, ?, ?, ?, ?, ?)''',
                        (session_id, user_id, token, device_id, device_name, expires_at)
                    )
                    await self._db.commit()
                    return True
                except aiosqlite.IntegrityError:
                    return False
    
    async def get_session_by_token(self, token: str) -> Optional[Dict]:
        """Get session by token"""
        async with self._db.cursor() as cursor:
            await cursor.execute(
                'SELECT * FROM sessions WHERE token = ? AND (expires_at IS NULL OR expires_at > ?)',
                (token, time.time())
            )
            row = await cursor.fetchone()
            if row:
                return dict(row)
            return None
    
    async def delete_session(self, token: str):
        """Delete a session"""
        async with self._lock:
            async with self._db.cursor() as cursor:
                await cursor.execute('DELETE FROM sessions WHERE token = ?', (token,))
                await self._db.commit()
    
    async def update_session_activity(self, token: str):
        """Update session last activity"""
        async with self._db.cursor() as cursor:
            await cursor.execute(
                'UPDATE sessions SET last_activity = ? WHERE token = ?',
                (time.time(), token)
            )
            await self._db.commit()
    
    # Contact operations
    async def add_contact(self, user_id: str, contact_id: str) -> bool:
        """Add a contact"""
        async with self._lock:
            async with self._db.cursor() as cursor:
                try:
                    await cursor.execute(
                        'INSERT INTO contacts (user_id, contact_id) VALUES (?, ?)',
                        (user_id, contact_id)
                    )
                    await self._db.commit()
                    return True
                except aiosqlite.IntegrityError:
                    return False
    
    async def remove_contact(self, user_id: str, contact_id: str):
        """Remove a contact"""
        async with self._lock:
            async with self._db.cursor() as cursor:
                await cursor.execute(
                    'DELETE FROM contacts WHERE user_id = ? AND contact_id = ?',
                    (user_id, contact_id)
                )
                await self._db.commit()
    
    async def block_contact(self, user_id: str, contact_id: str):
        """Block a contact"""
        async with self._lock:
            async with self._db.cursor() as cursor:
                await cursor.execute(
                    'INSERT OR REPLACE INTO contacts (user_id, contact_id, is_blocked) VALUES (?, ?, 1)',
                    (user_id, contact_id)
                )
                await self._db.commit()
    
    async def get_contacts(self, user_id: str) -> List[Dict]:
        """Get user's contacts"""
        async with self._db.cursor() as cursor:
            await cursor.execute(
                '''SELECT c.contact_id, c.is_blocked, u.username, u.display_name, u.status, u.last_seen
                   FROM contacts c
                   JOIN users u ON c.contact_id = u.id
                   WHERE c.user_id = ?''',
                (user_id,)
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    
    # Chat operations
    async def create_chat(self, chat_id: str, name: Optional[str], chat_type: str, 
                         created_by: str) -> bool:
        """Create a new chat"""
        async with self._lock:
            async with self._db.cursor() as cursor:
                try:
                    await cursor.execute(
                        '''INSERT INTO chats (id, name, type, created_by)
                           VALUES (?, ?, ?, ?)''',
                        (chat_id, name, chat_type, created_by)
                    )
                    await self._db.commit()
                    return True
                except aiosqlite.IntegrityError:
                    return False
    
    async def add_chat_member(self, chat_id: str, user_id: str, role: str = 'member'):
        """Add member to chat"""
        async with self._lock:
            async with self._db.cursor() as cursor:
                await cursor.execute(
                    '''INSERT OR REPLACE INTO chat_members (chat_id, user_id, role)
                       VALUES (?, ?, ?)''',
                    (chat_id, user_id, role)
                )
                await cursor.execute(
                    'UPDATE chats SET updated_at = ? WHERE id = ?',
                    (time.time(), chat_id)
                )
                await self._db.commit()
    
    async def remove_chat_member(self, chat_id: str, user_id: str):
        """Remove member from chat"""
        async with self._lock:
            async with self._db.cursor() as cursor:
                await cursor.execute(
                    'DELETE FROM chat_members WHERE chat_id = ? AND user_id = ?',
                    (chat_id, user_id)
                )
                await cursor.execute(
                    'UPDATE chats SET updated_at = ? WHERE id = ?',
                    (time.time(), chat_id)
                )
                await self._db.commit()
    
    async def get_chat_members(self, chat_id: str) -> List[Dict]:
        """Get chat members"""
        async with self._db.cursor() as cursor:
            await cursor.execute(
                '''SELECT cm.user_id, cm.role, u.username, u.display_name, u.status
                   FROM chat_members cm
                   JOIN users u ON cm.user_id = u.id
                   WHERE cm.chat_id = ?''',
                (chat_id,)
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    
    async def get_user_chats(self, user_id: str) -> List[Dict]:
        """Get all chats for a user"""
        async with self._db.cursor() as cursor:
            await cursor.execute(
                '''SELECT c.*, cm.role
                   FROM chats c
                   JOIN chat_members cm ON c.id = cm.chat_id
                   WHERE cm.user_id = ?
                   ORDER BY c.updated_at DESC''',
                (user_id,)
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    
    async def get_chat(self, chat_id: str) -> Optional[Dict]:
        """Get chat by ID"""
        async with self._db.cursor() as cursor:
            await cursor.execute('SELECT * FROM chats WHERE id = ?', (chat_id,))
            row = await cursor.fetchone()
            if row:
                return dict(row)
            return None
    
    # Message operations
    async def create_message(self, message_id: str, chat_id: str, sender_id: str,
                            content: str, content_type: str = 'text',
                            reply_to: Optional[str] = None) -> bool:
        """Create a new message"""
        async with self._lock:
            async with self._db.cursor() as cursor:
                try:
                    await cursor.execute(
                        '''INSERT INTO messages 
                           (id, chat_id, sender_id, content, content_type, reply_to)
                           VALUES (?, ?, ?, ?, ?, ?)''',
                        (message_id, chat_id, sender_id, content, content_type, reply_to)
                    )
                    await cursor.execute(
                        'UPDATE chats SET updated_at = ? WHERE id = ?',
                        (time.time(), chat_id)
                    )
                    await self._db.commit()
                    return True
                except Exception as e:
                    print(f"Error creating message: {e}")
                    return False
    
    async def get_messages(self, chat_id: str, limit: int = 50, 
                          before: Optional[float] = None) -> List[Dict]:
        """Get messages for a chat"""
        async with self._db.cursor() as cursor:
            if before:
                await cursor.execute(
                    '''SELECT m.*, u.username as sender_username, u.display_name as sender_display_name
                       FROM messages m
                       JOIN users u ON m.sender_id = u.id
                       WHERE m.chat_id = ? AND m.created_at < ? AND m.deleted = 0
                       ORDER BY m.created_at DESC
                       LIMIT ?''',
                    (chat_id, before, limit)
                )
            else:
                await cursor.execute(
                    '''SELECT m.*, u.username as sender_username, u.display_name as sender_display_name
                       FROM messages m
                       JOIN users u ON m.sender_id = u.id
                       WHERE m.chat_id = ? AND m.deleted = 0
                       ORDER BY m.created_at DESC
                       LIMIT ?''',
                    (chat_id, limit)
                )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    
    async def edit_message(self, message_id: str, content: str, user_id: str) -> bool:
        """Edit a message"""
        async with self._lock:
            async with self._db.cursor() as cursor:
                await cursor.execute(
                    '''UPDATE messages SET content = ?, edited = 1, updated_at = ?
                       WHERE id = ? AND sender_id = ?''',
                    (content, time.time(), message_id, user_id)
                )
                await self._db.commit()
                return cursor.rowcount > 0
    
    async def delete_message(self, message_id: str, user_id: str) -> bool:
        """Delete a message (soft delete)"""
        async with self._lock:
            async with self._db.cursor() as cursor:
                await cursor.execute(
                    'UPDATE messages SET deleted = 1, updated_at = ? WHERE id = ? AND sender_id = ?',
                    (time.time(), message_id, user_id)
                )
                await self._db.commit()
                return cursor.rowcount > 0
    
    async def mark_message_read(self, message_id: str, user_id: str):
        """Mark message as read"""
        async with self._lock:
            async with self._db.cursor() as cursor:
                await cursor.execute(
                    'INSERT OR IGNORE INTO read_receipts (message_id, user_id) VALUES (?, ?)',
                    (message_id, user_id)
                )
                await self._db.commit()
    
    async def get_unread_count(self, chat_id: str, user_id: str) -> int:
        """Get unread message count for a chat"""
        async with self._db.cursor() as cursor:
            await cursor.execute(
                '''SELECT COUNT(*) as count
                   FROM messages m
                   LEFT JOIN read_receipts rr ON m.id = rr.message_id AND rr.user_id = ?
                   WHERE m.chat_id = ? AND m.sender_id != ? AND rr.message_id IS NULL AND m.deleted = 0''',
                (user_id, chat_id, user_id)
            )
            row = await cursor.fetchone()
            return row['count'] if row else 0
    
    # Attachment operations
    async def add_attachment(self, attachment_id: str, message_id: str,
                            filename: str, filepath: str, filesize: int,
                            mime_type: Optional[str] = None):
        """Add attachment to message"""
        async with self._lock:
            async with self._db.cursor() as cursor:
                await cursor.execute(
                    '''INSERT INTO attachments (id, message_id, filename, filepath, filesize, mime_type)
                       VALUES (?, ?, ?, ?, ?, ?)''',
                    (attachment_id, message_id, filename, filepath, filesize, mime_type)
                )
                await self._db.commit()
    
    async def get_attachments(self, message_id: str) -> List[Dict]:
        """Get attachments for a message"""
        async with self._db.cursor() as cursor:
            await cursor.execute(
                'SELECT * FROM attachments WHERE message_id = ?',
                (message_id,)
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    
    # Settings operations
    async def get_setting(self, key: str, default: str = None) -> Optional[str]:
        """Get server setting"""
        async with self._db.cursor() as cursor:
            await cursor.execute('SELECT value FROM server_settings WHERE key = ?', (key,))
            row = await cursor.fetchone()
            return row['value'] if row else default
    
    async def set_setting(self, key: str, value: str):
        """Set server setting"""
        async with self._lock:
            async with self._db.cursor() as cursor:
                await cursor.execute(
                    'INSERT OR REPLACE INTO server_settings (key, value, updated_at) VALUES (?, ?, ?)',
                    (key, value, time.time())
                )
                await self._db.commit()
