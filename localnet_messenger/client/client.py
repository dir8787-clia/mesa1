#!/usr/bin/env python3
"""
LocalNet Messenger - Client Launcher
Main entry point for the desktop client application
"""
import sys
import os
import asyncio
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from client.network.connection import NetworkManager
from client.gui.main_window import AuthDialog, MainWindow, run_client_app


def create_app():
    """Create and configure Qt application"""
    app = QApplication(sys.argv)
    app.setApplicationName("LocalNet Messenger")
    app.setOrganizationName("LocalNet Project")
    app.setStyle('Fusion')
    
    # Set application-wide font
    font = QFont("Segoe UI", 10)
    if not font.exactMatch():
        font = QFont("Arial", 10)
    app.setFont(font)
    
    return app


async def run_auth_and_connect(network: NetworkManager):
    """Show auth dialog and connect to server"""
    dialog = AuthDialog()
    
    if dialog.exec() != QDialog.Accepted:
        return False
    
    data = dialog.get_data()
    
    # Validate input
    if not data['username'] or len(data['username']) < 3:
        QMessageBox.critical(
            None,
            "Ошибка",
            "Имя пользователя должно быть не менее 3 символов"
        )
        return False
    
    if not data['password'] or len(data['password']) < 6:
        QMessageBox.critical(
            None,
            "Ошибка",
            "Пароль должен быть не менее 6 символов"
        )
        return False
    
    # Connect to server
    connected = await network.connect(data['server'], data['port'])
    
    if not connected:
        QMessageBox.critical(
            None,
            "Ошибка подключения",
            f"Не удалось подключиться к серверу {data['server']}:{data['port']}\n\n"
            "Убедитесь, что сервер запущен и доступен в вашей сети."
        )
        return False
    
    # Register or login
    if dialog.result_type == 'register':
        result = await network.register(
            data['username'],
            data['password'],
            data['display_name']
        )
        
        if not result.get('success'):
            QMessageBox.critical(
                None,
                "Ошибка регистрации",
                result.get('error', 'Неизвестная ошибка')
            )
            return False
        
        # Auto-login after registration
        login_result = await network.login(data['username'], data['password'])
        if not login_result.get('success'):
            return False
            
    else:
        result = await network.login(data['username'], data['password'])
        
        if not result.get('success'):
            QMessageBox.critical(
                None,
                "Ошибка входа",
                result.get('error', 'Неизвестная ошибка')
            )
            return False
    
    return True


def main():
    """Main entry point"""
    # Create Qt app
    app = create_app()
    
    # Create network manager
    network = NetworkManager()
    
    async def setup_and_run():
        # Start network manager
        await network.start()
        
        # Run authentication
        auth_success = await run_auth_and_connect(network)
        
        if not auth_success:
            await network.stop()
            return 1
        
        # Run main window
        from client.gui.main_window import MainWindow
        window = MainWindow(network)
        window.show()
        
        return app.exec()
    
    # Run async setup then start Qt event loop
    try:
        # For platforms without display, we can't run GUI
        if os.environ.get('DISPLAY') is None and sys.platform != 'darwin' and 'win' not in sys.platform:
            print("GUI requires a display. Running in headless mode is not supported.")
            print("\nTo use LocalNet Messenger:")
            print("1. On Linux: Ensure X11/Wayland is available")
            print("2. On Windows/macOS: Run directly")
            print("\nServer can be started with: python -m localnet_messenger.server.server")
            return 1
        
        result = asyncio.run(setup_and_run())
        return result
        
    except KeyboardInterrupt:
        print("\nShutting down...")
        asyncio.run(network.stop())
        return 0
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
