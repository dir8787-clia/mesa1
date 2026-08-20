"""
LocalNet Messenger - Client GUI Module
Main window, auth dialog, and UI components
"""

import sys
from typing import Optional, Dict, Any, List
from datetime import datetime

from PySide6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QListWidget, QListWidgetItem, QTextEdit, QSplitter,
    QWidget, QFrame, QScrollArea, QMessageBox, QMenu,
    QSystemTrayIcon, QComboBox, QFileDialog, QProgressBar, QGroupBox,
    QCheckBox, QSpinBox, QTabWidget, QDialogButtonBox, QFormLayout
)
from PySide6.QtCore import Qt, Signal, QObject, QTimer, QUrl, QSize
from PySide6.QtGui import QFont, QIcon, QPixmap, QColor, QPalette, QTextCursor, QAction

from shared.protocol import MessageType, ProtocolMessage


class AuthDialog(QDialog):
    """Authentication dialog for login/registration"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("LocalNet Messenger")
        self.setMinimumWidth(400)
        self.result_type = 'login'  # 'login' or 'register'
        
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(15)
        
        # Title
        title = QLabel("LocalNet Messenger")
        title.setAlignment(Qt.AlignCenter)
        title_font = QFont("Segoe UI", 18, QFont.Bold)
        title.setFont(title_font)
        layout.addWidget(title)
        
        # Server settings
        server_group = QGroupBox("Server Settings")
        server_layout = QFormLayout()
        
        self.server_input = QLineEdit("127.0.0.1")
        self.server_input.setPlaceholderText("Server IP or hostname")
        server_layout.addRow("Server:", self.server_input)
        
        self.port_input = QLineEdit("8765")
        self.port_input.setPlaceholderText("Port")
        self.port_input.setMaximumWidth(80)
        server_layout.addRow("Port:", self.port_input)
        
        server_group.setLayout(server_layout)
        layout.addWidget(server_group)
        
        # Credentials
        creds_group = QGroupBox("Credentials")
        creds_layout = QFormLayout()
        
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Enter username")
        creds_layout.addRow("Username:", self.username_input)
        
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Enter password")
        self.password_input.setEchoMode(QLineEdit.Password)
        creds_layout.addRow("Password:", self.password_input)
        
        self.display_name_input = QLineEdit()
        self.display_name_input.setPlaceholderText("Optional display name")
        self.display_name_input.setVisible(False)
        creds_layout.addRow("Display Name:", self.display_name_input)
        
        creds_group.setLayout(creds_layout)
        layout.addWidget(creds_group)
        
        # Mode switch
        mode_layout = QHBoxLayout()
        mode_layout.addStretch()
        
        self.mode_label = QLabel("Don't have an account?")
        mode_layout.addWidget(self.mode_label)
        
        self.mode_button = QPushButton("Register")
        self.mode_button.clicked.connect(self.toggle_mode)
        mode_layout.addWidget(self.mode_button)
        
        layout.addLayout(mode_layout)
        
        # Action buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.action_button = QPushButton("Login")
        self.action_button.setMinimumWidth(100)
        self.action_button.clicked.connect(self.accept)
        button_layout.addWidget(self.action_button)
        
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
    def toggle_mode(self):
        if self.result_type == 'login':
            self.result_type = 'register'
            self.mode_label.setText("Already have an account?")
            self.mode_button.setText("Login")
            self.action_button.setText("Register")
            self.display_name_input.setVisible(True)
        else:
            self.result_type = 'login'
            self.mode_label.setText("Don't have an account?")
            self.mode_button.setText("Register")
            self.action_button.setText("Login")
            self.display_name_input.setVisible(False)
    
    def get_data(self) -> Dict[str, Any]:
        return {
            'server': self.server_input.text().strip() or '127.0.0.1',
            'port': int(self.port_input.text().strip() or '8765'),
            'username': self.username_input.text().strip(),
            'password': self.password_input.text(),
            'display_name': self.display_name_input.text().strip()
        }


class MessageBubble(QFrame):
    """Chat message bubble widget"""
    
    def __init__(self, content: str, is_own: bool = False, timestamp: float = None, parent=None):
        super().__init__(parent)
        self.is_own = is_own
        self.timestamp = timestamp
        
        self.setup_ui(content)
    
    def setup_ui(self, content: str):
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 5, 10, 5)
        
        # Message text
        self.text_label = QLabel(content)
        self.text_label.setWordWrap(True)
        self.text_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.text_label)
        
        # Timestamp
        if self.timestamp:
            time_str = datetime.fromtimestamp(self.timestamp).strftime("%H:%M")
            time_label = QLabel(time_str)
            time_label.setStyleSheet("color: gray; font-size: 10px;")
            if self.is_own:
                time_label.setAlignment(Qt.AlignRight)
            layout.addWidget(time_label)
        
        self.setLayout(layout)
        
        # Style based on sender
        if self.is_own:
            self.setStyleSheet("""
                MessageBubble {
                    background-color: #dcf8c6;
                    border-radius: 10px;
                    margin: 2px;
                }
            """)
            self.text_label.setStyleSheet("padding: 5px;")
        else:
            self.setStyleSheet("""
                MessageBubble {
                    background-color: #ffffff;
                    border-radius: 10px;
                    margin: 2px;
                }
            """)
            self.text_label.setStyleSheet("padding: 5px;")


class ChatListWidget(QListWidget):
    """Custom list widget for chat list"""
    
    chat_selected = Signal(int)  # chat_id
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)
    
    def show_context_menu(self, pos):
        item = self.itemAt(pos)
        if not item:
            return
        
        menu = QMenu()
        menu.addAction("Open Chat")
        menu.addAction("Clear History")
        menu.exec_(self.viewport().mapToGlobal(pos))


class MainWindow(QWidget):
    """Main application window"""
    
    def __init__(self, network_manager, parent=None):
        super().__init__(parent)
        self.network = network_manager
        self.current_chat_id: Optional[int] = None
        self.chats: List[Dict] = []
        self.users: List[Dict] = []
        self.messages: Dict[int, List[Dict]] = {}  # chat_id -> messages
        
        self.setup_ui()
        self.setup_handlers()
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.refresh_data)
        self.update_timer.start(5000)  # Refresh every 5 seconds
    
    def setup_ui(self):
        self.setWindowTitle("LocalNet Messenger")
        self.setMinimumSize(900, 600)
        
        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Left panel - Chat list
        left_panel = QWidget()
        left_layout = QVBoxLayout()
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        # Search box
        search_input = QLineEdit()
        search_input.setPlaceholderText("Search chats...")
        search_input.setMaximumHeight(30)
        left_layout.addWidget(search_input)
        
        # Chat list
        self.chat_list = ChatListWidget()
        self.chat_list.itemClicked.connect(self.on_chat_selected)
        left_layout.addWidget(self.chat_list)
        
        # New chat button
        new_chat_btn = QPushButton("+ New Chat")
        new_chat_btn.clicked.connect(self.create_new_chat)
        left_layout.addWidget(new_chat_btn)
        
        left_panel.setLayout(left_layout)
        
        # Right panel - Messages
        right_panel = QWidget()
        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        # Chat header
        self.chat_header = QLabel("Select a chat")
        self.chat_header.setStyleSheet("font-weight: bold; padding: 10px; background-color: #f0f0f0;")
        right_layout.addWidget(self.chat_header)
        
        # Messages area
        self.messages_scroll = QScrollArea()
        self.messages_scroll.setWidgetResizable(True)
        self.messages_widget = QWidget()
        self.messages_layout = QVBoxLayout()
        self.messages_layout.addStretch()
        self.messages_widget.setLayout(self.messages_layout)
        self.messages_scroll.setWidget(self.messages_widget)
        right_layout.addWidget(self.messages_scroll)
        
        # Input area
        input_layout = QHBoxLayout()
        
        self.message_input = QTextEdit()
        self.message_input.setPlaceholderText("Type a message...")
        self.message_input.setMaximumHeight(100)
        self.message_input.setMinimumHeight(60)
        input_layout.addWidget(self.message_input)
        
        send_btn = QPushButton("Send")
        send_btn.clicked.connect(self.send_message)
        send_btn.setMinimumWidth(80)
        input_layout.addWidget(send_btn)
        
        right_layout.addLayout(input_layout)
        
        right_panel.setLayout(right_layout)
        
        # Add panels to main layout
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([250, 650])
        
        main_layout.addWidget(splitter)
        self.setLayout(main_layout)
        
        # Setup system tray
        self.setup_tray()
    
    def setup_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(QIcon.fromTheme("message"))
        self.tray_icon.setToolTip("LocalNet Messenger")
        self.tray_icon.show()
    
    def setup_handlers(self):
        # Register message handlers
        self.network.register_handler(MessageType.MESSAGE_SEND.value, self.on_message_received)
        self.network.register_handler(MessageType.PRESENCE_UPDATE.value, self.on_presence_update)
    
    def refresh_data(self):
        """Refresh chat and user lists"""
        asyncio.ensure_future(self.load_chats())
        asyncio.ensure_future(self.load_users())
    
    async def load_chats(self):
        """Load chat list from server"""
        chats = await self.network.get_chat_list()
        self.chats = chats
        self.update_chat_list_ui()
    
    async def load_users(self):
        """Load user list from server"""
        users = await self.network.get_user_list()
        self.users = users
    
    def update_chat_list_ui(self):
        """Update chat list UI"""
        self.chat_list.clear()
        
        for chat in self.chats:
            item = QListWidgetItem()
            
            # Create chat info widget
            chat_widget = QWidget()
            chat_layout = QVBoxLayout()
            chat_layout.setContentsMargins(5, 5, 5, 5)
            
            chat_name = chat.get('name') or f"Chat #{chat['id']}"
            name_label = QLabel(chat_name)
            name_label.setStyleSheet("font-weight: bold;")
            chat_layout.addWidget(name_label)
            
            last_msg = chat.get('last_message')
            if last_msg:
                preview = last_msg.get('content', '')[:50]
                if len(last_msg.get('content', '')) > 50:
                    preview += "..."
                sender = last_msg.get('sender_username', '')
                preview_label = QLabel(f"{sender}: {preview}" if sender else preview)
                preview_label.setStyleSheet("color: gray; font-size: 11px;")
                chat_layout.addWidget(preview_label)
            
            chat_widget.setLayout(chat_layout)
            
            item.setSizeHint(chat_widget.sizeHint())
            self.chat_list.addItem(item)
            self.chat_list.setItemWidget(item, chat_widget)
    
    def on_chat_selected(self, item):
        """Handle chat selection"""
        index = self.chat_list.row(item)
        if 0 <= index < len(self.chats):
            chat = self.chats[index]
            self.current_chat_id = chat['id']
            self.chat_header.setText(chat.get('name') or f"Chat #{chat['id']}")
            self.load_messages_for_chat(chat['id'])
    
    def load_messages_for_chat(self, chat_id: int):
        """Load messages for a specific chat"""
        # Clear current messages
        while self.messages_layout.count():
            child = self.messages_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        
        # Get messages from storage or show empty state
        messages = self.messages.get(chat_id, [])
        
        if not messages:
            empty_label = QLabel("No messages yet. Start the conversation!")
            empty_label.setAlignment(Qt.AlignCenter)
            empty_label.setStyleSheet("color: gray; padding: 20px;")
            self.messages_layout.insertWidget(0, empty_label)
        else:
            for msg in messages:
                self.add_message_to_ui(msg)
    
    def add_message_to_ui(self, msg: Dict):
        """Add a message to the UI"""
        is_own = msg.get('sender_id') == self.network.user_id
        bubble = MessageBubble(
            msg.get('content', ''),
            is_own=is_own,
            timestamp=msg.get('created_at')
        )
        
        # Insert before the stretch
        self.messages_layout.insertWidget(self.messages_layout.count() - 1, bubble)
        
        # Scroll to bottom
        scrollbar = self.messages_scroll.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    def on_message_received(self, msg: ProtocolMessage):
        """Handle incoming message"""
        payload = msg.payload
        chat_id = payload.get('chat_id')
        
        # Store message
        if chat_id not in self.messages:
            self.messages[chat_id] = []
        self.messages[chat_id].append(payload)
        
        # Update UI if this is the current chat
        if chat_id == self.current_chat_id:
            self.add_message_to_ui(payload)
    
    def on_presence_update(self, msg: ProtocolMessage):
        """Handle presence update"""
        users = msg.payload.get('users', [])
        # Update user statuses in UI
        pass
    
    def send_message(self):
        """Send current message"""
        if not self.current_chat_id:
            QMessageBox.warning(self, "Warning", "Please select a chat first")
            return
        
        content = self.message_input.toPlainText().strip()
        if not content:
            return
        
        asyncio.ensure_future(self.network.send_message_to_chat(
            self.current_chat_id,
            content
        ))
        
        self.message_input.clear()
    
    def create_new_chat(self):
        """Create a new chat"""
        dialog = QDialog(self)
        dialog.setWindowTitle("New Chat")
        layout = QVBoxLayout()
        
        # Chat type
        type_combo = QComboBox()
        type_combo.addItems(["Personal", "Group"])
        layout.addRow("Type:", type_combo)
        
        # For group chats
        name_input = QLineEdit()
        name_input.setPlaceholderText("Group name (for groups)")
        layout.addRow("Name:", name_input)
        
        # User selection (simplified)
        user_list = QListWidget()
        user_list.setSelectionMode(QListWidget.MultiSelection)
        for user in self.users:
            user_list.addItem(f"{user.get('display_name') or user['username']} ({user['username']})")
        layout.addRow("Members:", user_list)
        
        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        
        dialog.setLayout(layout)
        
        if dialog.exec_() == QDialog.Accepted:
            # Create chat logic here
            pass


def run_client_app():
    """Run the client application"""
    app = QApplication(sys.argv)
    app.setApplicationName("LocalNet Messenger")
    
    # Show main window (would need network manager)
    # window = MainWindow(network_manager)
    # window.show()
    
    sys.exit(app.exec_())
