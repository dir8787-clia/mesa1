"""
SoftDeploy - Telegram Bot Integration
"""
import requests


def send_telegram_message(config, message):
    """Отправка сообщения в Telegram"""
    telegram_config = config.get('telegram', {})
    
    if not telegram_config.get('enabled', False):
        return False
    
    bot_token = telegram_config.get('bot_token')
    chat_id = telegram_config.get('chat_id')
    
    if not bot_token or not chat_id:
        return False
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    
    data = {
        'chat_id': chat_id,
        'text': message,
        'parse_mode': 'HTML'
    }
    
    try:
        response = requests.post(url, json=data, timeout=10)
        return response.status_code == 200
    except Exception as e:
        print(f"Telegram notification error: {e}")
        return False


def send_deploy_notification(config, deploy_run, package, event_type='start'):
    """Отправка уведомления о развёртывании"""
    if event_type == 'start':
        emoji = '🚀'
        status = 'ЗАПУЩЕНО'
    elif event_type == 'success':
        emoji = '✅'
        status = 'УСПЕШНО ЗАВЕРШЕНО'
    elif event_type == 'failed':
        emoji = '❌'
        status = 'ОШИБКА'
    else:
        emoji = 'ℹ️'
        status = 'ИНФО'
    
    message = f"{emoji} <b>SoftDeploy - {status}</b>\n\n"
    message += f"Пакет: <b>{package.name}</b> v{package.version}\n"
    message += f"Цель: {deploy_run.target_name}\n"
    
    if deploy_run.started_by:
        from app.models import User
        user = User.query.get(deploy_run.started_by)
        if user:
            message += f"Пользователь: {user.username}\n"
    
    if event_type == 'success':
        message += f"Код возврата: {deploy_run.exit_code}\n"
    elif event_type == 'failed' and deploy_run.error_message:
        message += f"Ошибка: {deploy_run.error_message}\n"
    
    message += f"\nВремя: {deploy_run.started_at.strftime('%Y-%m-%d %H:%M:%S')}"
    
    return send_telegram_message(config, message)
