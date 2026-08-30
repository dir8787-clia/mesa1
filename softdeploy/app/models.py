"""
SoftDeploy - Database Models
"""
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(UserMixin, db.Model):
    """Модель пользователя приложения"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), default='user')  # 'admin' или 'user'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def __repr__(self):
        return f'<User {self.username}>'


class Group(db.Model):
    """Модель отдела/группы ПК"""
    __tablename__ = 'groups'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    
    hosts = db.relationship('Host', backref='group', lazy='dynamic')
    packages = db.relationship('Package', secondary='package_groups', back_populates='target_groups')
    
    def __repr__(self):
        return f'<Group {self.name}>'


class Host(db.Model):
    """Модель компьютера (хоста)"""
    __tablename__ = 'hosts'
    
    id = db.Column(db.Integer, primary_key=True)
    hostname = db.Column(db.String(255), unique=True, nullable=False, index=True)
    ip_address = db.Column(db.String(45))  # Поддержка IPv6
    group_id = db.Column(db.Integer, db.ForeignKey('groups.id'), nullable=True)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    last_seen = db.Column(db.DateTime)
    
    versions = db.relationship('HostVersion', backref='host', lazy='dynamic', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Host {self.hostname}>'


class Package(db.Model):
    """Модель пакета ПО"""
    __tablename__ = 'packages'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    app_name = db.Column(db.String(200), nullable=False)  # Имя в реестре Windows
    version = db.Column(db.String(50), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    silent_keys = db.Column(db.String(500))  # Ключи тихой установки
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    deploy_to_all = db.Column(db.Boolean, default=False)  # Ставить на все ПК
    
    target_groups = db.relationship('Package', secondary='package_groups', back_populates='packages')
    deploy_runs = db.relationship('DeployRun', backref='package', lazy='dynamic')
    
    def __repr__(self):
        return f'<Package {self.name} v{self.version}>'


class PackageGroup(db.Model):
    """Таблица связи пакетов и групп (многие-ко-многим)"""
    __tablename__ = 'package_groups'
    
    package_id = db.Column(db.Integer, db.ForeignKey('packages.id'), primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('groups.id'), primary_key=True)
    
    packages = db.relationship('Package', back_populates='target_groups')
    groups = db.relationship('Group', back_populates='packages')


class DeployRun(db.Model):
    """Модель запуска развёртывания"""
    __tablename__ = 'deploy_runs'
    
    id = db.Column(db.Integer, primary_key=True)
    package_id = db.Column(db.Integer, db.ForeignKey('packages.id'), nullable=False)
    target_type = db.Column(db.String(20), nullable=False)  # 'all', 'group', 'host'
    target_id = db.Column(db.Integer)  # ID группы или хоста, NULL если 'all'
    target_name = db.Column(db.String(255))  # Имя цели для отображения
    status = db.Column(db.String(20), default='pending')  # pending, running, success, failed, partial
    started_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    exit_code = db.Column(db.Integer)
    log_file = db.Column(db.String(255))
    error_message = db.Column(db.Text)
    
    starter = db.relationship('User', backref='deploy_runs')
    
    def __repr__(self):
        return f'<DeployRun {self.id} - {self.status}>'


class HostVersion(db.Model):
    """Модель кэша версий ПО на хостах"""
    __tablename__ = 'host_versions'
    
    id = db.Column(db.Integer, primary_key=True)
    host_id = db.Column(db.Integer, db.ForeignKey('hosts.id'), nullable=False, index=True)
    package_id = db.Column(db.Integer, db.ForeignKey('packages.id'), nullable=False)
    installed_version = db.Column(db.String(50))
    last_checked = db.Column(db.DateTime, default=datetime.utcnow)
    install_status = db.Column(db.String(20), default='unknown')  # unknown, installed, not_installed, mismatch
    
    package = db.relationship('Package', backref='version_records')
    
    __table_args__ = (db.UniqueConstraint('host_id', 'package_id', name='uq_host_package'),)
    
    def __repr__(self):
        return f'<HostVersion host={self.host_id} package={self.package_id}>'


class Schedule(db.Model):
    """Модель расписания развёртывания"""
    __tablename__ = 'schedules'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    cron_expression = db.Column(db.String(100), nullable=False)  # Формат cron: "мин час день мес день_нед"
    package_id = db.Column(db.Integer, db.ForeignKey('packages.id'), nullable=False)
    target_type = db.Column(db.String(20), nullable=False)  # 'all', 'group', 'host'
    target_id = db.Column(db.Integer)
    target_name = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_run = db.Column(db.DateTime)
    next_run = db.Column(db.DateTime)
    job_id = db.Column(db.String(100))  # ID задачи APScheduler
    
    package = db.relationship('Package', backref='schedules')
    
    def __repr__(self):
        return f'<Schedule {self.name}>'
