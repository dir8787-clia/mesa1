#!/bin/bash
# SoftDeploy - Installation Script for Debian 13

set -e

echo "=========================================="
echo "  SoftDeploy Installation Script"
echo "  For Debian 13 (Trixie)"
echo "=========================================="

# Проверка root прав
if [ "$EUID" -ne 0 ]; then 
    echo "Ошибка: Запустите скрипт от root"
    exit 1
fi

# Создание директорий
echo "[1/8] Создание директорий..."
mkdir -p /srv/softdeploy/{app,packages,logs,reports,templates,static}
chmod 750 /srv/softdeploy
chmod 750 /srv/softdeploy/packages
chmod 750 /srv/softdeploy/logs
chmod 750 /srv/softdeploy/reports

# Установка системных зависимостей
echo "[2/8] Установка системных зависимостей..."
apt-get update
apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    ansible \
    krb5-user \
    libkrb5-dev \
    winrm \
    git \
    curl

# Создание виртуального окружения
echo "[3/8] Создание Python virtualenv..."
python3 -m venv /srv/softdeploy/venv
source /srv/softdeploy/venv/bin/activate

# Установка Python зависимостей
echo "[4/8] Установка Python пакетов..."
pip install --upgrade pip
pip install \
    Flask==3.0.0 \
    Flask-Login==0.6.3 \
    Flask-SQLAlchemy==3.1.1 \
    Flask-WTF==1.2.1 \
    Werkzeug==3.0.1 \
    SQLAlchemy==2.0.23 \
    APScheduler==3.10.4 \
    PyYAML==6.0.1 \
    requests==2.31.0 \
    ansible==9.0.0 \
    pywinrm==0.4.3 \
    pypsrp==0.8.1

# Копирование файлов приложения
echo "[5/8] Копирование файлов приложения..."
# Файлы должны быть уже скопированы в /srv/softdeploy

# Создание конфигурации
echo "[6/8] Создание конфигурации..."
if [ ! -f /srv/softdeploy/config.yml ]; then
    cat > /srv/softdeploy/config.yml << 'YAML'
database:
  path: /srv/softdeploy/softdeploy.db

flask:
  secret_key: "CHANGE_THIS_SECRET_KEY_IN_PRODUCTION_$(openssl rand -hex 32)"
  debug: false

winrm:
  port: 5985
  transport: ntlm
  username: "administrator@vdk.local"

domain:
  name: "vdk.local"
  realm: "VDK.LOCAL"

telegram:
  enabled: false
  bot_token: ""
  chat_id: ""

paths:
  packages: /srv/softdeploy/packages
  logs: /srv/softdeploy/logs
  reports: /srv/softdeploy/reports

security:
  vault_key_file: /srv/softdeploy/ansible_vault_key.txt
  allowed_extensions: [".exe", ".msi"]
  max_file_size_mb: 500

scheduler:
  enabled: true
  timezone: "Europe/Moscow"
YAML
    chmod 640 /srv/softdeploy/config.yml
fi

# Генерация ключа для ansible-vault
echo "[7/8] Генерация ключа ansible-vault..."
if [ ! -f /srv/softdeploy/ansible_vault_key.txt ]; then
    openssl rand -base64 32 > /srv/softdeploy/ansible_vault_key.txt
    chmod 600 /srv/softdeploy/ansible_vault_key.txt
fi

# Создание systemd службы
echo "[8/8] Настройка systemd службы..."
cat > /etc/systemd/system/softdeploy.service << 'SYSTEMD'
[Unit]
Description=SoftDeploy - Software Deployment System
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/srv/softdeploy
Environment="PATH=/srv/softdeploy/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ExecStart=/srv/softdeploy/venv/bin/gunicorn --bind 0.0.0.0:8080 --workers 4 "app:create_app()"
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SYSTEMD

# Установка gunicorn
pip install gunicorn

echo ""
echo "=========================================="
echo "  Установка завершена!"
echo "=========================================="
echo ""
echo "Дальнейшие шаги:"
echo "1. Создайте администратора:"
echo "   cd /srv/softdeploy && ./venv/bin/python create_admin.py admin <password>"
echo ""
echo "2. Запустите службу:"
echo "   systemctl daemon-reload"
echo "   systemctl enable softdeploy"
echo "   systemctl start softdeploy"
echo ""
echo "3. Откройте в браузере: http://192.168.1.178:8080"
echo ""
echo "=========================================="
