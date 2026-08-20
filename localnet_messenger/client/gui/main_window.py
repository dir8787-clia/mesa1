#!/usr/bin/env python3
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
        
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        # Title
        title = QLabel("LocalNet Messenger")
        title.setFont(QFont("Segoe UI", 18, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        subtitle = QLabel("Вход в локальную сеть")
        subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(subtitle)
        
        # Server settings
        server_group = QGroupBox("Сервер")
        server_layout = QFormLayout(server_group)
        
        self.server_input = QLineEdit("127.0.0.1")
        self.server_input.setPlaceholderText("IP адрес сервера")
        server_layout.addRow("Адрес:", self.server_input)
        
        self.port_input = QLineEdit("8765")
        self.port_input.setPlaceholderText("Порт")
        self.port_input.setMaximumWidth(80)
        server_layout.addRow("Порт:", self.port_input)
        
        layout.addWidget(server_group)
        
        # Credentials
        creds_group = QGroupBox("Учетные данные")
        creds_layout = QFormLayout(creds_group)
        
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Имя пользователя")
        creds_layout.addRow("Имя:", self.username_input)
        
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Пароль")
        self.password_input.setEchoMode(QLineEdit.Password)
        creds_layout.addRow("Пароль:", self.password_input)
        
        self.display_name_input = QLineEdit()
        self.display_name_input.setPlaceholderText("Отображаемое имя")
        self.display_name_input.setVisible(False)
        creds_layout.addRow("Имя:", self.display_name_input)
        
        layout.addWidget(creds_group)
        
        # Toggle between login/register
        self.toggle_btn = QPushButton("Нет аккаунта? Зарегистрироваться")
        self.toggle_btn.clicked.connect(self._toggle_mode)
        layout.addWidget(self.toggle_btn)
        
        # Submit button
        self.submit_btn = QPushButton("Войти")
        self.submit_btn.setDefault(True)
        self.submit_btn.clicked.connect(self._submit)
        layout.addWidget(self.submit_btn)
    
    def _toggle_mode(self):
        if self.result_type == 'login':
            self.result_type = 'register'
            self.setWindowTitle("Регистрация")
            self.submit_btn.setText("Зарегистрироваться")
            self.toggle_btn.setText("Есть аккаунт? Войти")
            self.display_name_input.setVisible(True)
        else:
            self.result_type = 'login'
            self.setWindowTitle("Вход")
            self.submit_btn.setText("Войти")
            self.toggle_btn.setText("Нет аккаунта? Зарегистрироваться")
            self.display_name_input.setVisible(False)
    
    def _submit(self):
        self.accept()
    
    def get_data(self) -> Dict[str, Any]:
        return {
            'server': self.server_input.text().strip() or '127.0.0.1',
            'port': int(self.port_input.text().strip() or '8765'),
            'username': self.username_input.text().strip(),
            'password': self.password_input.text(),
            'display_name': self.display_name_input.text().strip() or None
        }


class ChatListWidget(QWidget):
    """Widget displaying list of chats"""
    
    chat_selected = Signal(str)  # chat_id
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.chats: Dict[str, Dict] = {}
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Header
        header = QLabel("Чаты")
        header.setFont(QFont("Segoe UI", 12, QFont.Bold))
        layout.addWidget(header)
        
        # Chat list
        self.list_widget = QListWidget()
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self.list_widget)
        
        # New chat button
        new_chat_btn = QPushButton("+ Новый чат")
        new_chat_btn.clicked.connect(self._new_chat)
        layout.addWidget(new_chat_btn)
    
    def _on_item_clicked(self, item: QListWidgetItem):
        chat_id = item.data(Qt.UserRole)
        if chat_id:
            self.chat_selected.emit(chat_id)
    
    def _new_chat(self):
        # Would open dialog to create new chat
        pass
    
    def update_chats(self, chats: List[Dict]):
        self.list_widget.clear()
        self.chats = {}
        
        for chat in chats:
            chat_id = chat.get('id')
            name = chat.get('name', 'Unknown')
            chat_type = chat.get('type', 'private')
            
            item = QListWidgetItem(f"{'👥' if chat_type == 'group' else '👤'} {name}")
            item.setData(Qt.UserRole, chat_id)
            self.list_widget.addItem(item)
            self.chats[chat_id] = chat


class MessageView(QWidget):
    """Widget displaying messages in a chat"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.messages: List[Dict] = []
        self.current_chat_id: Optional[str] = None
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Chat header
        self.header_label = QLabel("Выберите чат")
        self.header_label.setFont(QFont("Segoe UI", 14, QFont.Bold))
        layout.addWidget(self.header_label)
        
        # Messages area
        self.messages_area = QTextEdit()
        self.messages_area.setReadOnly(True)
        self.messages_area.setMinimumHeight(300)
        layout.addWidget(self.messages_area)
        
        # Input area
        input_layout = QHBoxLayout()
        
        self.message_input = QTextEdit()
        self.message_input.setMaximumHeight(100)
        self.message_input.setPlaceholderText("Введите сообщение...")
        input_layout.addWidget(self.message_input)
        
        send_btn = QPushButton("Отправить")
        send_btn.clicked.connect(self._send_message)
        input_layout.addWidget(send_btn)
        
        layout.addLayout(input_layout)
    
    def _send_message(self):
        content = self.message_input.toPlainText().strip()
        if content and self.current_chat_id:
            # Emit signal for network manager to send
            self.message_sent.emit(self.current_chat_id, content)
            self.message_input.clear()
    
    def set_chat(self, chat_id: str, chat_name: str):
        self.current_chat_id = chat_id
        self.header_label.setText(chat_name)
        self.messages_area.clear()
        self.messages = []
    
    def add_message(self, msg: Dict):
        self.messages.append(msg)
        
        sender = msg.get('sender_display_name', msg.get('sender_id', 'Unknown'))
        content = msg.get('content', '')
        timestamp = msg.get('created_at', 0)
        time_str = datetime.fromtimestamp(timestamp).strftime("%H:%M")
        
        # Format message
        html = f"""
        <div style="margin: 5px 0;">
            <b>{sender}</b> <small style="color: gray;">{time_str}</small><br>
            {content.replace('\n', '<br>')}
        </div>
        """
        
        cursor = self.messages_area.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertHtml(html)
        self.messages_area.setTextCursor(cursor)
    
    def load_history(self, messages: List[Dict]):
        self.messages_area.clear()
        self.messages = messages
        
        # Sort by timestamp
        sorted_msgs = sorted(messages, key=lambda m: m.get('created_at', 0))
        
        for msg in sorted_msgs:
            self.add_message(msg)
    
    message_sent = Signal(str, str)  # chat_id, content


class MainWindow(QWidget):
    """Main application window"""
    
    def __init__(self, network_manager, parent=None):
        super().__init__(parent)
        self.network = network_manager
        self.current_chat_id: Optional[str] = None
        
        self._setup_ui()
        self._setup_connections()
    
    def _setup_ui(self):
        self.setWindowTitle("LocalNet Messenger")
        self.setMinimumSize(900, 600)
        
        layout = QHBoxLayout(self)
        
        # Left panel - chat list
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        # User info
        self.user_label = QLabel("")
        self.user_label.setFont(QFont("Segoe UI", 10, QFont.Bold))
        left_layout.addWidget(self.user_label)
        
        # Chat list
        self.chat_list = ChatListWidget()
        left_layout.addWidget(self.chat_list)
        
        layout.addWidget(left_panel, stretch=1)
        
        # Right panel - messages
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        self.message_view = MessageView()
        right_layout.addWidget(self.message_view)
        
        layout.addWidget(right_panel, stretch=3)
    
    def _setup_connections(self):
        self.chat_list.chat_selected.connect(self._on_chat_selected)
        self.message_view.message_sent.connect(self._on_message_sent)
        
        # Register network handlers
        self.network.register_handler('message.send', self._on_incoming_message)
        self.network.register_handler('chat.list', self._on_chat_list)
        self.network.register_handler('user.list', self._on_user_list)
    
    def _on_chat_selected(self, chat_id: str):
        self.current_chat_id = chat_id
        chat_info = self.chat_list.chats.get(chat_id, {})
        chat_name = chat_info.get('name', 'Chat')
        self.message_view.set_chat(chat_id, chat_name)
        
        # Load history
        asyncio.ensure_future(self._load_chat_history(chat_id))
    
    async def _load_chat_history(self, chat_id: str):
        result = await self.network.get_message_history(chat_id)
        if result.get('success'):
            messages = result.get('messages', [])
            self.message_view.load_history(messages)
    
    def _on_message_sent(self, chat_id: str, content: str):
        asyncio.ensure_future(self.network.send_message(chat_id, content))
    
    def _on_incoming_message(self, msg: ProtocolMessage):
        if msg.payload.get('chat_id') == self.current_chat_id:
            self.message_view.add_message(msg.payload)
    
    def _on_chat_list(self, msg: ProtocolMessage):
        if msg.payload.get('success'):
            chats = msg.payload.get('chats', [])
            self.chat_list.update_chats(chats)
    
    def _on_user_list(self, msg: ProtocolMessage):
        if msg.payload.get('success'):
            users = msg.payload.get('users', [])
            # Could show users in a separate panel
    
    def showEvent(self, event):
        super().showEvent(event)
        # Load initial data
        asyncio.ensure_future(self._load_initial_data())
    
    async def _load_initial_data(self):
        # Get user info
        self.user_label.setText(f"Пользователь: {self.network.username}")
        
        # Get chat list
        result = await self.network.get_chat_list()
        if result.get('success'):
            self.chat_list.update_chats(result.get('chats', []))
        
        # Get user list
        await self.network.get_user_list()


# Import asyncio at module level for use in signals
import asyncio


def run_client_app():
    """Run the client application"""
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    # Set font
    font = QFont("Segoe UI", 10)
    app.setFont(font)
    
    # Show auth dialog
    dialog = AuthDialog()
    if dialog.exec() != QDialog.Accepted:
        return 1
    
    data = dialog.get_data()
    
    # Validate
    if len(data['username']) < 3:
        QMessageBox.critical(None, "Ошибка", "Имя должно быть не менее 3 символов")
        return 1
    
    if len(data['password']) < 6:
        QMessageBox.critical(None, "Ошибка", "Пароль должен быть не менее 6 символов")
        return 1
    
    # Create network manager
    from client.network.connection import NetworkManager
    network = NetworkManager()
    
    async def setup():
        await network.start()
        
        # Connect
        connected = await network.connect(data['server'], data['port'])
        if not connected:
            QMessageBox.critical(None, "Ошибка", f"Не удалось подключиться к {data['server']}:{data['port']}")
            return None
        
        # Login or register
        if dialog.result_type == 'register':
            result = await network.register(data['username'], data['password'], data['display_name'])
            if not result.get('success'):
                QMessageBox.critical(None, "Ошибка регистрации", result.get('error'))
                return None
            # Auto-login
            result = await network.login(data['username'], data['password'])
        else:
            result = await network.login(data['username'], data['password'])
        
        if not result.get('success'):
            QMessageBox.critical(None, "Ошибка входа", result.get('error'))
            return None
        
        return network
    
    # Run setup
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        network = loop.run_until_complete(setup())
        if not network:
            return 1
        
        # Show main window
        window = MainWindow(network)
        window.show()
        
        return app.exec()
    finally:
        loop.close()
