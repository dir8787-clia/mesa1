#!/usr/bin/env python3
"""
SoftDeploy - Script for creating admin user
Usage: python3 create_admin.py <username> <password>
"""
import sys
import os

# Добавляем путь к приложению
sys.path.insert(0, '/srv/softdeploy')
os.chdir('/srv/softdeploy')

from app import create_app, db
from app.models import User

def create_admin(username, password):
    """Создание пользователя с правами администратора"""
    app = create_app()
    
    with app.app_context():
        # Проверка существования пользователя
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            print(f"Пользователь '{username}' уже существует!")
            return False
        
        # Создание админа
        admin = User(
            username=username,
            role='admin'
        )
        admin.set_password(password)
        
        db.session.add(admin)
        db.session.commit()
        
        print(f"Администратор '{username}' успешно создан!")
        return True

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Использование: python3 create_admin.py <username> <password>")
        print("Пример: python3 create_admin.py admin MySecurePass123")
        sys.exit(1)
    
    username = sys.argv[1]
    password = sys.argv[2]
    
    if len(password) < 6:
        print("Ошибка: пароль должен быть не менее 6 символов!")
        sys.exit(1)
    
    success = create_admin(username, password)
    sys.exit(0 if success else 1)
