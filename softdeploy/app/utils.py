"""
SoftDeploy - Utility Functions
"""
import os
import hashlib


def generate_secret_key():
    """Генерация безопасного секретного ключа"""
    return hashlib.sha256(os.urandom(32)).hexdigest()


def get_file_hash(filepath):
    """Вычисление хеша файла (SHA256)"""
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def format_file_size(size_bytes):
    """Форматирование размера файла"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} TB"


def parse_cron_to_human(cron_expr):
    """Преобразование cron выражения в человекочитаемый формат"""
    parts = cron_expr.strip().split()
    if len(parts) != 5:
        return cron_expr
    
    minute, hour, day, month, dow = parts
    
    dow_names = {
        '0': 'Воскресенье', '1': 'Понедельник', '2': 'Вторник',
        '3': 'Среда', '4': 'Четверг', '5': 'Пятница', '6': 'Суббота'
    }
    
    result = []
    
    if minute == '*':
        result.append('каждую минуту')
    else:
        result.append(f'в {minute} мин')
    
    if hour == '*':
        result.append('каждый час')
    else:
        result.append(f'в {hour} час')
    
    if day != '*':
        result.append(f'{day} числа')
    
    if month != '*':
        result.append(f'{month} месяца')
    
    if dow != '*':
        days = [dow_names.get(d, d) for d in dow.split(',')]
        result.append(f'по {" ".join(days)}')
    
    return ', '.join(result)
