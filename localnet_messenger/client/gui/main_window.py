"""
LocalNet Messenger Client - Main GUI Application
Intuitive desktop interface with PySide6/Qt
"""
import sys
import os
import asyncio
from pathlib import Path
from typing import Optional, Dict, List
import logging
import json
from datetime import datetime

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QListWidget, QListWidgetItem, QTextEdit, QLineEdit,
    QPushButton, QLabel, QStackedWidget, QFrame, QScrollArea,
    QFileDialog, QMessageBox, QMenu, QSystemTrayIcon,
    QDialog, QDialogButtonBox, QFormLayout, QComboBox, QCheckBox,
    QProgressBar, QToolBar, QStatusBar, QTabWidget, QGroupBox,
    QSpinBox, QStyle
)
from PySide6.QtCore import Qt, QTimer, Signal, QObject, QThread, QSize, QUrl
from PySide6.QtGui import QFont, QIcon, QPixmap, QPainter, QColor, QBrush, QAction

# Import protocol types
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from shared.protocol import MessageType, ProtocolMessage

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AuthDialog(QDialog):
    """Login/Register dialog"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("LocalNet Messenger - Вход")
        self.setMinimumSize(400, 350)
        self.setModal(True)
        
        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(30, 30, 30, 30)
        
        # Title
        title = QLabel("LocalNet Messenger")
        title.setFont(QFont("Arial", 18, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        subtitle = QLabel("Локальный мессенджер для вашей сети")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("color: gray;")
        layout.addWidget(subtitle)
        
        layout.addSpacing(20)
        
        # Form
        form_layout = QFormLayout()
        form_layout.setSpacing(10)
        
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Имя пользователя")
        self.username_input.setMinimumHeight(35)
        form_layout.addRow("", self.username_input)
        
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Пароль")
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setMinimumHeight(35)
        form_layout.addRow("", self.password_input)
        
        self.display_name_input = QLineEdit()
        self.display_name_input.setPlaceholderText("Отображаемое имя (необязательно)")
        self.display_name_input.setMinimumHeight(35)
        form_layout.addRow("", self.display_name_input)
        
        layout.addLayout(form_layout)
        
        # Status label
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: red;")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        
        layout.addSpacing(10)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        
        self.login_button = QPushButton("Войти")
        self.login_button.setMinimumHeight(40)
        self.login_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        button_layout.addWidget(self.login_button)
        
        self.register_button = QPushButton("Регистрация")
        self.register_button.setMinimumHeight(40)
        self.register_button.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
        """)
        button_layout.addWidget(self.register_button)
        
        layout.addLayout(button_layout)
        
        # Server connection
        server_layout = QHBoxLayout()
        server_layout.addWidget(QLabel("Сервер:"))
        self.server_input = QLineEdit()
        self.server_input.setPlaceholderText("IP адрес или hostname")
        self.server_input.setText("localhost")
        server_layout.addWidget(self.server_input)
        
        self.port_input = QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(8765)
        server_layout.addWidget(self.port_input)
        
        layout.addLayout(server_layout)
        
        self.setLayout(layout)
        
        # Connections
        self.login_button.clicked.connect(self.on_login)
        self.register_button.clicked.connect(self.on_register)
        self.username_input.returnPressed.connect(self.on_login)
        self.password_input.returnPressed.connect(self.on_login)
    
    def on_login(self):
        self.accept()
        self.result_type = 'login'
    
    def on_register(self):
        if not self.display_name_input.text():
            self.display_name_input.setText(self.username_input.text())
        self.accept()
        self.result_type = 'register'
    
    def get_data(self):
        return {
            'username': self.username_input.text().strip(),
            'password': self.password_input.text(),
            'display_name': self.display_name_input.text().strip(),
            'server': self.server_input.text().strip(),
            'port': self.port_input.value()
        }
    
    def set_error(self, message):
        self.status_label.setText(message)


class ChatListWidget(QWidget):
    """Widget displaying list of chats"""
    
    chat_selected = Signal(str)  # chat_id
    
    def __init__(self):
        super().__init__()
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header
        header = QLabel("Чаты")
        header.setFont(QFont("Arial", 14, QFont.Bold))
        header.setStyleSheet("padding: 10px; background-color: #f0f0f0;")
        layout.addWidget(header)
        
        # Chat list
        self.chat_list = QListWidget()
        self.chat_list.setStyleSheet("""
            QListWidget {
                border: none;
                outline: none;
            }
            QListWidget::item {
                padding: 10px;
                border-bottom: 1px solid #e0e0e0;
            }
            QListWidget::item:selected {
                background-color: #e3f2fd;
            }
            QListWidget::item:hover {
                background-color: #f5f5f5;
            }
        """)
        self.chat_list.itemClicked.connect(self.on_chat_clicked)
        layout.addWidget(self.chat_list)
        
        self.setLayout(layout)
    
    def on_chat_clicked(self, item):
        chat_id = item.data(Qt.UserRole)
        if chat_id:
            self.chat_selected.emit(chat_id)
    
    def update_chats(self, chats: List[Dict]):
        self.chat_list.clear()
        for chat in chats:
            item = QListWidgetItem()
            
            # Create chat item widget
            chat_widget = QWidget()
            chat_layout = QHBoxLayout()
            chat_layout.setContentsMargins(10, 10, 10, 10)
            
            # Avatar placeholder
            avatar = QLabel()
            avatar.setFixedSize(40, 40)
            avatar.setStyleSheet("""
                QLabel {
                    background-color: #2196F3;
                    color: white;
                    border-radius: 20px;
                    font-weight: bold;
                    font-size: 16px;
                }
            """)
            avatar.setAlignment(Qt.AlignCenter)
            
            # Set initial letter
            name = chat.get('name', 'Chat')
            avatar.setText(name[0].upper() if name else '?')
            
            chat_layout.addWidget(avatar)
            
            # Info
            info_layout = QVBoxLayout()
            
            name_label = QLabel(name)
            name_label.setFont(QFont("Arial", 12, QFont.Bold))
            info_layout.addWidget(name_label)
            
            last_msg = chat.get('last_message', {})
            if last_msg:
                preview = last_msg.get('content', '')[:50]
                time_str = datetime.fromtimestamp(last_msg.get('created_at', 0)).strftime("%H:%M")
                
                preview_label = QLabel(f"{time_str}  {preview}")
                preview_label.setStyleSheet("color: gray; font-size: 11px;")
                info_layout.addWidget(preview_label)
            
            info_layout.addStretch()
            chat_layout.addLayout(info_layout)
            
            chat_widget.setLayout(chat_layout)
            
            item.setSizeHint(chat_widget.sizeHint())
            item.setData(Qt.UserRole, chat.get('id'))
            
            self.chat_list.addItem(item)
            self.chat_list.setItemWidget(item, chat_widget)


class MessageViewWidget(QWidget):
    """Widget displaying messages in a chat"""
    
    send_message = Signal(str, str)  # content, chat_id
    
    def __init__(self):
        super().__init__()
        self.current_chat_id = None
        self.typing_timer = QTimer()
        self.typing_timer.setSingleShot(True)
        self.typing_timer.timeout.connect(self._stop_typing)
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Messages area
        self.messages_scroll = QScrollArea()
        self.messages_scroll.setWidgetResizable(True)
        self.messages_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.messages_scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: white;
            }
        """)
        
        self.messages_container = QWidget()
        self.messages_layout = QVBoxLayout()
        self.messages_layout.setSpacing(10)
        self.messages_layout.setContentsMargins(15, 15, 15, 15)
        self.messages_layout.addStretch()
        self.messages_container.setLayout(self.messages_layout)
        
        self.messages_scroll.setWidget(self.messages_container)
        layout.addWidget(self.messages_scroll)
        
        # Typing indicator
        self.typing_label = QLabel("")
        self.typing_label.setStyleSheet("color: gray; font-style: italic; padding: 5px 15px;")
        self.typing_label.hide()
        layout.addWidget(self.typing_label)
        
        # Input area
        input_frame = QFrame()
        input_frame.setStyleSheet("""
            QFrame {
                background-color: #f5f5f5;
                border-top: 1px solid #e0e0e0;
            }
        """)
        input_layout = QHBoxLayout()
        input_layout.setContentsMargins(10, 10, 10, 10)
        input_layout.setSpacing(10)
        
        # File button
        self.file_button = QPushButton("📎")
        self.file_button.setFixedSize(40, 40)
        self.file_button.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                font-size: 18px;
                border-radius: 20px;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
        """)
        self.file_button.clicked.connect(self.on_file_click)
        input_layout.addWidget(self.file_button)
        
        # Message input
        self.message_input = QTextEdit()
        self.message_input.setPlaceholderText("Напишите сообщение...")
        self.message_input.setMaximumHeight(120)
        self.message_input.setMinimumHeight(40)
        self.message_input.setStyleSheet("""
            QTextEdit {
                border: 1px solid #ddd;
                border-radius: 20px;
                padding: 10px 15px;
                background-color: white;
            }
            QTextEdit:focus {
                border: 1px solid #2196F3;
            }
        """)
        self.message_input.installEventFilter(self)
        input_layout.addWidget(self.message_input)
        
        # Send button
        self.send_button = QPushButton("➤")
        self.send_button.setFixedSize(40, 40)
        self.send_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border-radius: 20px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        self.send_button.clicked.connect(self.on_send_click)
        input_layout.addWidget(self.send_button)
        
        input_frame.setLayout(input_layout)
        layout.addWidget(input_frame)
        
        self.setLayout(layout)
    
    def eventFilter(self, obj, event):
        if obj == self.message_input and event.type() == event.KeyPress:
            if event.key() == Qt.Key_Return and not event.modifiers() & Qt.ShiftModifier:
                self.on_send_click()
                return True
            elif event.key() == Qt.Key_Return and event.modifiers() & Qt.ShiftModifier:
                return False
        return super().eventFilter(obj, event)
    
    def on_send_click(self):
        content = self.message_input.toPlainText().strip()
        if content and self.current_chat_id:
            self.send_message.emit(content, self.current_chat_id)
            self.message_input.clear()
            self.typing_timer.start(2000)  # Reset typing timer
    
    def on_file_click(self):
        # Will be connected to actual file selection
        pass
    
    def _stop_typing(self):
        # Send typing stop signal
        pass
    
    def set_current_chat(self, chat_id: str):
        self.current_chat_id = chat_id
        self.clear_messages()
    
    def clear_messages(self):
        # Clear all message widgets except stretch
        while self.messages_layout.count() > 1:
            item = self.messages_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
    
    def add_message(self, message: Dict, is_own: bool):
        """Add a message bubble"""
        bubble = QWidget()
        bubble.setStyleSheet("""
            QWidget {
                border-radius: 15px;
                padding: 10px 15px;
                max-width: 400px;
            }
        """)
        
        bubble_layout = QVBoxLayout()
        bubble_layout.setSpacing(5)
        
        # Content
        content = message.get('content', '')
        content_label = QLabel(content)
        content_label.setWordWrap(True)
        content_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        bubble_layout.addWidget(content_label)
        
        # Time
        created_at = message.get('created_at', 0)
        time_str = datetime.fromtimestamp(created_at).strftime("%H:%M") if created_at else ""
        time_label = QLabel(time_str)
        time_label.setStyleSheet("font-size: 10px; color: gray;")
        time_label.setAlignment(Qt.AlignRight)
        bubble_layout.addWidget(time_label)
        
        bubble.setLayout(bubble_layout)
        
        # Style based on sender
        if is_own:
            bubble.setStyleSheet("""
                QWidget {
                    background-color: #dcf8c6;
                    border-radius: 15px;
                    padding: 10px 15px;
                    max-width: 400px;
                }
            """)
            self.messages_layout.insertWidget(self.messages_layout.count() - 1, bubble, alignment=Qt.AlignRight)
        else:
            bubble.setStyleSheet("""
                QWidget {
                    background-color: #ffffff;
                    border: 1px solid #e0e0e0;
                    border-radius: 15px;
                    padding: 10px 15px;
                    max-width: 400px;
                }
            """)
            self.messages_layout.insertWidget(self.messages_layout.count() - 1, bubble, alignment=Qt.AlignLeft)
        
        # Scroll to bottom
        self.messages_scroll.verticalScrollBar().setValue(
            self.messages_scroll.verticalScrollBar().maximum()
        )
    
    def load_messages(self, messages: List[Dict], user_id: str):
        """Load multiple messages"""
        self.clear_messages()
        # Messages are in reverse order (newest first), so reverse them
        for msg in reversed(messages):
            is_own = msg.get('sender_id') == user_id
            self.add_message(msg, is_own)
    
    def show_typing(self, username: str):
        self.typing_label.setText(f"{username} печатает...")
        self.typing_label.show()
    
    def hide_typing(self):
        self.typing_label.hide()


class MainWindow(QMainWindow):
    """Main application window"""
    
    def __init__(self, network_manager):
        super().__init__()
        self.network = network_manager
        self.user_data = {}
        self.chats_data = {}
        self.typing_users = {}
        
        self.setup_ui()
        self.setup_network_handlers()
        self.load_saved_session()
    
    def setup_ui(self):
        self.setWindowTitle("LocalNet Messenger")
        self.setMinimumSize(900, 600)
        
        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Splitter
        splitter = QSplitter(Qt.Horizontal)
        
        # Left panel - Chat list
        self.chat_list_widget = ChatListWidget()
        self.chat_list_widget.chat_selected.connect(self.on_chat_selected)
        splitter.addWidget(self.chat_list_widget)
        
        # Right panel - Messages
        self.message_view = MessageViewWidget()
        self.message_view.send_message.connect(self.on_send_message)
        splitter.addWidget(self.message_view)
        
        splitter.setSizes([280, 620])
        splitter.setHandleWidth(1)
        
        main_layout.addWidget(splitter)
        central.setLayout(main_layout)
        
        # Menu bar
        self.create_menu_bar()
        
        # Status bar
        self.statusBar().showMessage("Не подключено")
        
        # System tray
        self.setup_tray()
    
    def create_menu_bar(self):
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("Файл")
        
        new_chat_action = QAction("Новый чат", self)
        new_chat_action.triggered.connect(self.on_new_chat)
        file_menu.addAction(new_chat_action)
        
        new_group_action = QAction("Новая группа", self)
        new_group_action.triggered.connect(self.on_new_group)
        file_menu.addAction(new_group_action)
        
        file_menu.addSeparator()
        
        settings_action = QAction("Настройки", self)
        settings_action.triggered.connect(self.on_settings)
        file_menu.addAction(settings_action)
        
        file_menu.addSeparator()
        
        logout_action = QAction("Выйти", self)
        logout_action.triggered.connect(self.on_logout)
        file_menu.addAction(logout_action)
        
        # Help menu
        help_menu = menubar.addMenu("Помощь")
        
        about_action = QAction("О программе", self)
        about_action.triggered.connect(self.on_about)
        help_menu.addAction(about_action)
    
    def setup_tray(self):
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray_icon = QSystemTrayIcon(self)
            self.tray_icon.setIcon(self.style().standardIcon(QStyle.SP_DesktopIcon))
            
            tray_menu = QMenu()
            show_action = tray_menu.addAction("Показать")
            show_action.triggered.connect(self.show)
            quit_action = tray_menu.addAction("Выход")
            quit_action.triggered.connect(QApplication.quit)
            
            self.tray_icon.setContextMenu(tray_menu)
            self.tray_icon.activated.connect(self.on_tray_activated)
            self.tray_icon.show()
    
    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.show()
            self.activateWindow()
    
    def setup_network_handlers(self):
        """Setup network message handlers"""
        nm = self.network
        
        nm.on_connected(self.on_connected)
        nm.on_disconnected(self.on_disconnected)
        nm.on_message(self.on_message_received)
        
        nm.register_handler(MessageType.AUTH_LOGIN.value, self.handle_auth_response)
        nm.register_handler(MessageType.MESSAGE_SEND.value, self.handle_new_message)
        nm.register_handler(MessageType.MESSAGE_HISTORY.value, self.handle_message_history)
        nm.register_handler(MessageType.CHAT_CREATE.value, self.handle_chat_created)
        nm.register_handler(MessageType.TYPING_START.value, self.handle_typing_start)
        nm.register_handler(MessageType.TYPING_STOP.value, self.handle_typing_stop)
        nm.register_handler(MessageType.PRESENCE_STATUS.value, self.handle_presence_update)
    
    def load_saved_session(self):
        """Load saved session from config"""
        config_path = Path.home() / '.localnet_messenger' / 'config.json'
        if config_path.exists():
            try:
                with open(config_path) as f:
                    config = json.load(f)
                    token = config.get('token')
                    server = config.get('server', 'localhost')
                    port = config.get('port', 8765)
                    
                    if token:
                        self.network.session_token = token
                        self.network.user_id = config.get('user_id')
                        self.network.username = config.get('username')
                        
                        # Auto-connect
                        asyncio.ensure_future(self.network.connect(server, port))
            except Exception as e:
                logger.error(f"Error loading saved session: {e}")
    
    def save_session(self):
        """Save session to config"""
        config_dir = Path.home() / '.localnet_messenger'
        config_dir.mkdir(parents=True, exist_ok=True)
        
        config = {
            'token': self.network.session_token,
            'user_id': self.network.user_id,
            'username': self.network.username,
            'server': self.network.server_host,
            'port': self.network.server_port
        }
        
        with open(config_dir / 'config.json', 'w') as f:
            json.dump(config, f)
    
    def on_connected(self):
        """Called when connected to server"""
        self.statusBar().showMessage(f"Подключено к {self.network.server_host}")
        self.statusBar().setStyleSheet("background-color: #c8e6c9;")
    
    def on_disconnected(self):
        """Called when disconnected from server"""
        self.statusBar().showMessage("Отключено от сервера")
        self.statusBar().setStyleSheet("background-color: #ffcdd2;")
    
    def on_message_received(self, msg: ProtocolMessage):
        """General message handler"""
        pass
    
    def handle_auth_response(self, msg: ProtocolMessage):
        """Handle login response"""
        payload = msg.payload
        if payload.get('success'):
            self.user_data = payload
            self.save_session()
            
            # Load chats
            chats = payload.get('chats', [])
            self.chats_data = {c['id']: c for c in chats}
            self.update_chat_list()
    
    def handle_new_message(self, msg: ProtocolMessage):
        """Handle incoming message"""
        payload = msg.payload
        chat_id = payload.get('chat_id')
        message = payload.get('message')
        
        if chat_id in self.chats_data:
            # Update chat preview
            self.chats_data[chat_id]['last_message'] = message
            self.update_chat_list()
            
            # Add to message view if this chat is open
            if self.message_view.current_chat_id == chat_id:
                is_own = message.get('sender_id') == self.network.user_id
                self.message_view.add_message(message, is_own)
                
                # Mark as read
                if not is_own:
                    asyncio.ensure_future(self.network.mark_read(chat_id))
    
    def handle_message_history(self, msg: ProtocolMessage):
        """Handle message history response"""
        payload = msg.payload
        messages = payload.get('messages', [])
        self.message_view.load_messages(messages, self.network.user_id)
    
    def handle_chat_created(self, msg: ProtocolMessage):
        """Handle new chat notification"""
        payload = msg.payload
        chat = payload.get('chat')
        if chat:
            self.chats_data[chat['id']] = chat
            self.update_chat_list()
    
    def handle_typing_start(self, msg: ProtocolMessage):
        """Handle typing indicator"""
        payload = msg.payload
        chat_id = payload.get('chat_id')
        user_id = payload.get('user_id')
        
        if chat_id == self.message_view.current_chat_id and user_id != self.network.user_id:
            # Get username
            username = "Пользователь"
            self.message_view.show_typing(username)
    
    def handle_typing_stop(self, msg: ProtocolMessage):
        """Handle typing stop"""
        self.message_view.hide_typing()
    
    def handle_presence_update(self, msg: ProtocolMessage):
        """Handle presence update"""
        pass
    
    def on_chat_selected(self, chat_id: str):
        """Handle chat selection"""
        if chat_id in self.chats_data:
            self.message_view.set_current_chat(chat_id)
            
            # Load message history
            asyncio.ensure_future(self.network.get_message_history(chat_id))
    
    def on_send_message(self, content: str, chat_id: str):
        """Handle sending message"""
        asyncio.ensure_future(self.network.send_message(chat_id, content))
    
    def on_new_chat(self):
        """Create new private chat"""
        # Show user selection dialog
        pass
    
    def on_new_group(self):
        """Create new group chat"""
        dialog = QDialog(self)
        dialog.setWindowTitle("Создать группу")
        layout = QVBoxLayout()
        
        name_input = QLineEdit()
        name_input.setPlaceholderText("Название группы")
        layout.addWidget(name_input)
        
        members_label = QLabel("Выберите участников:")
        layout.addWidget(members_label)
        
        members_list = QListWidget()
        layout.addWidget(members_list)
        
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        
        dialog.setLayout(layout)
        
        if dialog.exec() == QDialog.Accepted:
            name = name_input.text().strip()
            if name:
                # Get selected members
                selected = [item.data(Qt.UserRole) for item in members_list.selectedItems()]
                asyncio.ensure_future(self.network.create_group(name, selected))
    
    def on_settings(self):
        """Open settings dialog"""
        pass
    
    def on_logout(self):
        """Logout from server"""
        asyncio.ensure_future(self.network.logout())
        
        # Clear saved session
        config_path = Path.home() / '.localnet_messenger' / 'config.json'
        if config_path.exists():
            config_path.unlink()
        
        # Close window or show login again
        self.close()
    
    def on_about(self):
        """Show about dialog"""
        QMessageBox.about(
            self,
            "О LocalNet Messenger",
            "LocalNet Messenger v1.0\n\n"
            "Локальный мессенджер для безопасного общения в вашей сети.\n\n"
            "Технологии: Python, PySide6, WebSocket\n\n"
            "© 2024 LocalNet Project"
        )
    
    def update_chat_list(self):
        """Update chat list widget"""
        chats = list(self.chats_data.values())
        self.chat_list_widget.update_chats(chats)
    
    def closeEvent(self, event):
        """Handle window close"""
        if self.tray_icon.isVisible() and self.tray_icon.isSystemTrayAvailable():
            self.hide()
            event.ignore()
        else:
            event.accept()


def run_client_app(network_manager):
    """Run the Qt application"""
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    # Set application-wide font
    font = QFont("Segoe UI", 10)
    app.setFont(font)
    
    window = MainWindow(network_manager)
    window.show()
    
    sys.exit(app.exec())
