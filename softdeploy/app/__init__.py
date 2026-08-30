"""
SoftDeploy - Flask Application Initialization
"""
import os
import yaml
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime

# Инициализация расширений
db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()
scheduler = BackgroundScheduler()

def load_config(config_path='/srv/softdeploy/config.yml'):
    """Загрузка конфигурации из YAML файла"""
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

def create_app(config=None):
    """Factory function для создания приложения"""
    app = Flask(__name__)
    
    # Загрузка конфигурации
    if config is None:
        config = load_config()
    
    # Настройка Flask
    app.config['SECRET_KEY'] = config.get('flask', {}).get('secret_key', 'dev-key')
    app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{config.get('database', {}).get('path', '/srv/softdeploy/softdeploy.db')}"
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['UPLOAD_FOLDER'] = config.get('paths', {}).get('packages', '/srv/softdeploy/packages')
    app.config['MAX_CONTENT_LENGTH'] = config.get('security', {}).get('max_file_size_mb', 500) * 1024 * 1024
    
    # Сохранение конфигурации в приложении
    app.config['SOFTDEPLOY_CONFIG'] = config
    
    # Инициализация расширений
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    
    # Настройка LoginManager
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Пожалуйста, войдите для доступа к этой странице.'
    
    # Импорт моделей для создания таблиц
    from app.models import User, Group, Host, Package, DeployRun, HostVersion, Schedule, PackageGroup
    
    # Создание таблиц БД
    with app.app_context():
        db.create_all()
    
    # Регистрация blueprint'ов
    from app.routes import main_bp
    from app.auth import auth_bp
    from app.api import api_bp
    
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(api_bp, url_prefix='/api')
    
    # Запуск планировщика
    if config.get('scheduler', {}).get('enabled', True):
        from app.scheduler import init_scheduler
        init_scheduler(scheduler, app)
        scheduler.start()
    
    return app

@login_manager.user_loader
def load_user(user_id):
    """Загрузка пользователя по ID"""
    from app.models import User
    return User.query.get(int(user_id))
