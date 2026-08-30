"""
SoftDeploy - Main Routes
"""
import os
import uuid
from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, send_from_directory
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app.models import db, User, Group, Host, Package, DeployRun, HostVersion, Schedule, PackageGroup
from app.tasks import run_deploy_task
from app.telegram_bot import send_telegram_message

main_bp = Blueprint('main', __name__, template_folder='../templates')


def allowed_file(filename, allowed_extensions):
    """Проверка расширения файла"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions


@main_bp.route('/')
@login_required
def dashboard():
    """Главная панель"""
    stats = {
        'packages': Package.query.filter_by(is_active=True).count(),
        'hosts': Host.query.filter_by(is_active=True).count(),
        'groups': Group.query.filter_by(is_active=True).count(),
        'deploy_runs': DeployRun.query.count(),
        'schedules': Schedule.query.filter_by(is_active=True).count()
    }
    
    recent_runs = DeployRun.query.order_by(DeployRun.started_at.desc()).limit(5).all()
    
    return render_template('dashboard.html', stats=stats, recent_runs=recent_runs)


@main_bp.route('/packages')
@login_required
def packages():
    """Управление пакетами ПО"""
    packages = Package.query.order_by(Package.created_at.desc()).all()
    groups = Group.query.filter_by(is_active=True).all()
    return render_template('packages.html', packages=packages, groups=groups)


@main_bp.route('/packages/add', methods=['POST'])
@login_required
def add_package():
    """Добавление нового пакета"""
    name = request.form.get('name')
    app_name = request.form.get('app_name')
    version = request.form.get('version')
    silent_keys = request.form.get('silent_keys', '')
    description = request.form.get('description', '')
    deploy_to_all = request.form.get('deploy_to_all') == 'on'
    target_groups = request.form.getlist('target_groups')
    
    if not name or not app_name or not version:
        flash('Имя, имя приложения и версия обязательны.', 'error')
        return redirect(url_for('main.packages'))
    
    # Проверка файла
    config = current_app.config['SOFTDEPLOY_CONFIG']
    allowed_ext = config.get('security', {}).get('allowed_extensions', ['.exe', '.msi'])
    max_size = config.get('security', {}).get('max_file_size_mb', 500) * 1024 * 1024
    
    if 'file' not in request.files:
        flash('Файл установщика обязателен.', 'error')
        return redirect(url_for('main.packages'))
    
    file = request.files['file']
    
    if file.filename == '':
        flash('Файл не выбран.', 'error')
        return redirect(url_for('main.packages'))
    
    if file and allowed_file(file.filename, allowed_ext):
        filename = secure_filename(file.filename)
        # Добавляем UUID для уникальности
        ext = filename.rsplit('.', 1)[1].lower()
        unique_filename = f"{uuid.uuid4().hex}_{filename}"
        
        # Проверка размера
        file.seek(0, os.SEEK_END)
        size = file.tell()
        file.seek(0)
        
        if size > max_size:
            flash(f'Файл слишком большой. Максимум {max_size // 1024 // 1024} МБ.', 'error')
            return redirect(url_for('main.packages'))
        
        # Сохранение файла
        upload_folder = current_app.config['UPLOAD_FOLDER']
        os.makedirs(upload_folder, exist_ok=True)
        filepath = os.path.join(upload_folder, unique_filename)
        file.save(filepath)
        
        # Создание записи в БД
        package = Package(
            name=name,
            app_name=app_name,
            version=version,
            filename=unique_filename,
            silent_keys=silent_keys,
            description=description,
            deploy_to_all=deploy_to_all
        )
        db.session.add(package)
        db.session.flush()
        
        # Привязка к группам
        if target_groups:
            for group_id in target_groups:
                pg = PackageGroup(package_id=package.id, group_id=int(group_id))
                db.session.add(pg)
        
        db.session.commit()
        flash(f'Пакет "{name}" успешно добавлен.', 'success')
    else:
        flash(f'Недопустимый тип файла. Разрешены: {", ".join(allowed_ext)}', 'error')
    
    return redirect(url_for('main.packages'))


@main_bp.route('/packages/<int:package_id>/delete', methods=['POST'])
@login_required
def delete_package(package_id):
    """Удаление пакета"""
    package = Package.query.get_or_404(package_id)
    
    # Удаление файла
    upload_folder = current_app.config['UPLOAD_FOLDER']
    filepath = os.path.join(upload_folder, package.filename)
    if os.path.exists(filepath):
        os.remove(filepath)
    
    # Удаление записей о связи с группами
    PackageGroup.query.filter_by(package_id=package_id).delete()
    
    # Удаление пакета
    db.session.delete(package)
    db.session.commit()
    
    flash(f'Пакет "{package.name}" удалён.', 'success')
    return redirect(url_for('main.packages'))


@main_bp.route('/groups')
@login_required
def groups():
    """Управление отделами/группами"""
    groups = Group.query.order_by(Group.created_at.desc()).all()
    return render_template('groups.html', groups=groups)


@main_bp.route('/groups/add', methods=['POST'])
@login_required
def add_group():
    """Добавление группы"""
    name = request.form.get('name')
    description = request.form.get('description', '')
    
    if not name:
        flash('Имя группы обязательно.', 'error')
        return redirect(url_for('main.groups'))
    
    if Group.query.filter_by(name=name).first():
        flash('Группа с таким именем уже существует.', 'error')
        return redirect(url_for('main.groups'))
    
    group = Group(name=name, description=description)
    db.session.add(group)
    db.session.commit()
    
    flash(f'Группа "{name}" создана.', 'success')
    return redirect(url_for('main.groups'))


@main_bp.route('/groups/<int:group_id>/toggle', methods=['POST'])
@login_required
def toggle_group(group_id):
    """Включение/отключение группы"""
    group = Group.query.get_or_404(group_id)
    group.is_active = not group.is_active
    db.session.commit()
    
    status = 'активна' if group.is_active else 'отключена'
    flash(f'Группа "{group.name}" {status}.', 'success')
    return redirect(url_for('main.groups'))


@main_bp.route('/hosts')
@login_required
def hosts():
    """Управление хостами (ПК)"""
    hosts = Host.query.order_by(Host.hostname).all()
    groups = Group.query.filter_by(is_active=True).all()
    return render_template('hosts.html', hosts=hosts, groups=groups)


@main_bp.route('/hosts/add', methods=['POST'])
@login_required
def add_host():
    """Добавление хоста"""
    hostname = request.form.get('hostname')
    ip_address = request.form.get('ip_address', '')
    group_id = request.form.get('group_id')
    description = request.form.get('description', '')
    
    if not hostname:
        flash('Имя хоста обязательно.', 'error')
        return redirect(url_for('main.hosts'))
    
    if Host.query.filter_by(hostname=hostname).first():
        flash('Хост с таким именем уже существует.', 'error')
        return redirect(url_for('main.hosts'))
    
    host = Host(
        hostname=hostname,
        ip_address=ip_address,
        group_id=int(group_id) if group_id else None,
        description=description
    )
    db.session.add(host)
    db.session.commit()
    
    flash(f'Хост "{hostname}" добавлен.', 'success')
    return redirect(url_for('main.hosts'))


@main_bp.route('/hosts/<int:host_id>/toggle', methods=['POST'])
@login_required
def toggle_host(host_id):
    """Включение/отключение хоста"""
    host = Host.query.get_or_404(host_id)
    host.is_active = not host.is_active
    db.session.commit()
    
    status = 'активен' if host.is_active else 'отключен'
    flash(f'Хост "{host.hostname}" {status}.', 'success')
    return redirect(url_for('main.hosts'))


@main_bp.route('/hosts/<int:host_id>/update-version', methods=['POST'])
@login_required
def update_host_version(host_id):
    """Обновление версий ПО на хосте"""
    from app.tasks import check_versions_on_host
    
    host = Host.query.get_or_404(host_id)
    check_versions_on_host.delay(host)
    
    flash(f'Запрошено обновление версий для {host.hostname}.', 'info')
    return redirect(url_for('main.hosts'))


@main_bp.route('/deploy')
@login_required
def deploy():
    """Страница развёртывания"""
    packages = Package.query.filter_by(is_active=True).all()
    groups = Group.query.filter_by(is_active=True).all()
    hosts = Host.query.filter_by(is_active=True).all()
    return render_template('deploy.html', packages=packages, groups=groups, hosts=hosts)


@main_bp.route('/deploy/run', methods=['POST'])
@login_required
def run_deploy():
    """Запуск развёртывания"""
    package_id = request.form.get('package_id')
    target_type = request.form.get('target_type')
    target_id = request.form.get('target_id')
    
    if not package_id:
        flash('Выберите пакет.', 'error')
        return redirect(url_for('main.deploy'))
    
    package = Package.query.get_or_404(package_id)
    
    # Определение цели
    target_name = "Все ПК"
    if target_type == 'group' and target_id:
        group = Group.query.get(int(target_id))
        target_name = f"Группа: {group.name}" if group else "Группа"
    elif target_type == 'host' and target_id:
        host = Host.query.get(int(target_id))
        target_name = f"Хост: {host.hostname}" if host else "Хост"
    
    # Создание записи о запуске
    deploy_run = DeployRun(
        package_id=package_id,
        target_type=target_type,
        target_id=int(target_id) if target_id else None,
        target_name=target_name,
        status='pending',
        started_by=current_user.id
    )
    db.session.add(deploy_run)
    db.session.flush()
    
    # Запуск задачи в фоне
    run_deploy_task.delay(deploy_run.id)
    
    # Telegram уведомление
    config = current_app.config['SOFTDEPLOY_CONFIG']
    if config.get('telegram', {}).get('enabled', False):
        msg = f"🚀 Старт развёртывания\n" \
              f"Пакет: {package.name} v{package.version}\n" \
              f"Цель: {target_name}\n" \
              f"Пользователь: {current_user.username}"
        send_telegram_message(config, msg)
    
    flash(f'Развёртывание "{package.name}" запущено для: {target_name}', 'success')
    return redirect(url_for('main.deploy_history'))


@main_bp.route('/deploy/history')
@login_required
def deploy_history():
    """История развёртываний"""
    runs = DeployRun.query.order_by(DeployRun.started_at.desc()).limit(50).all()
    return render_template('deploy_history.html', runs=runs)


@main_bp.route('/deploy/<int:run_id>/log')
@login_required
def view_log(run_id):
    """Просмотр лога развёртывания"""
    run = DeployRun.query.get_or_404(run_id)
    
    if not run.log_file:
        flash('Лог файл не найден.', 'error')
        return redirect(url_for('main.deploy_history'))
    
    log_path = os.path.join(current_app.config['SOFTDEPLOY_CONFIG'].get('paths', {}).get('logs', '/srv/softdeploy/logs'), run.log_file)
    
    if os.path.exists(log_path):
        with open(log_path, 'r') as f:
            log_content = f.read()
        return render_template('log_view.html', run=run, log_content=log_content)
    else:
        flash('Файл лога не найден.', 'error')
        return redirect(url_for('main.deploy_history'))


@main_bp.route('/reports')
@login_required
def reports():
    """Отчёты по установленному ПО"""
    hosts = Host.query.filter_by(is_active=True).all()
    packages = Package.query.filter_by(is_active=True).all()
    
    # Сбор данных о версиях
    report_data = []
    for host in hosts:
        host_info = {
            'hostname': host.hostname,
            'group': host.group.name if host.group else 'Без группы',
            'versions': {}
        }
        for hv in host.versions:
            host_info['versions'][hv.package.name] = {
                'version': hv.installed_version,
                'status': hv.install_status,
                'last_checked': hv.last_checked
            }
        report_data.append(host_info)
    
    return render_template('reports.html', report_data=report_data, packages=packages)


@main_bp.route('/reports/update-all', methods=['POST'])
@login_required
def update_all_versions():
    """Принудительное обновление всех версий"""
    from app.tasks import check_all_versions
    
    check_all_versions.delay()
    flash('Запрошено обновление версий на всех хостах.', 'info')
    return redirect(url_for('main.reports'))


@main_bp.route('/schedules')
@login_required
def schedules():
    """Управление расписаниями"""
    schedules = Schedule.query.order_by(Schedule.created_at.desc()).all()
    packages = Package.query.filter_by(is_active=True).all()
    groups = Group.query.filter_by(is_active=True).all()
    return render_template('schedules.html', schedules=schedules, packages=packages, groups=groups)


@main_bp.route('/schedules/add', methods=['POST'])
@login_required
def add_schedule():
    """Добавление расписания"""
    from app.scheduler import add_scheduled_job
    
    name = request.form.get('name')
    cron_expression = request.form.get('cron_expression')
    package_id = request.form.get('package_id')
    target_type = request.form.get('target_type')
    target_id = request.form.get('target_id')
    
    if not name or not cron_expression or not package_id:
        flash('Все обязательные поля должны быть заполнены.', 'error')
        return redirect(url_for('main.schedules'))
    
    # Создание записи
    schedule = Schedule(
        name=name,
        cron_expression=cron_expression,
        package_id=package_id,
        target_type=target_type,
        target_id=int(target_id) if target_id and target_type != 'all' else None,
        target_name=request.form.get('target_name', '')
    )
    db.session.add(schedule)
    db.session.flush()
    
    # Добавление задачи в планировщик
    job_id = add_scheduled_job(schedule)
    schedule.job_id = job_id
    db.session.commit()
    
    flash(f'Расписание "{name}" создано.', 'success')
    return redirect(url_for('main.schedules'))


@main_bp.route('/schedules/<int:schedule_id>/toggle', methods=['POST'])
@login_required
def toggle_schedule(schedule_id):
    """Включение/отключение расписания"""
    from app.scheduler import remove_scheduled_job, add_scheduled_job
    
    schedule = Schedule.query.get_or_404(schedule_id)
    schedule.is_active = not schedule.is_active
    
    if schedule.is_active and schedule.job_id:
        add_scheduled_job(schedule)
    elif not schedule.is_active and schedule.job_id:
        remove_scheduled_job(schedule.job_id)
    
    db.session.commit()
    
    status = 'активно' if schedule.is_active else 'отключено'
    flash(f'Расписание "{schedule.name}" {status}.', 'success')
    return redirect(url_for('main.schedules'))


@main_bp.route('/schedules/<int:schedule_id>/delete', methods=['POST'])
@login_required
def delete_schedule(schedule_id):
    """Удаление расписания"""
    from app.scheduler import remove_scheduled_job
    
    schedule = Schedule.query.get_or_404(schedule_id)
    
    if schedule.job_id:
        remove_scheduled_job(schedule.job_id)
    
    db.session.delete(schedule)
    db.session.commit()
    
    flash(f'Расписание "{schedule.name}" удалено.', 'success')
    return redirect(url_for('main.schedules'))


@main_bp.route('/settings')
@login_required
def settings():
    """Настройки системы"""
    config = current_app.config['SOFTDEPLOY_CONFIG']
    telegram_config = config.get('telegram', {})
    return render_template('settings.html', telegram_config=telegram_config)


@main_bp.route('/settings/telegram', methods=['POST'])
@login_required
def update_telegram_settings():
    """Обновление настроек Telegram"""
    import yaml
    
    enabled = request.form.get('telegram_enabled') == 'on'
    bot_token = request.form.get('bot_token', '')
    chat_id = request.form.get('chat_id', '')
    
    config_path = '/srv/softdeploy/config.yml'
    config = current_app.config['SOFTDEPLOY_CONFIG']
    
    if 'telegram' not in config:
        config['telegram'] = {}
    
    config['telegram']['enabled'] = enabled
    config['telegram']['bot_token'] = bot_token
    config['telegram']['chat_id'] = chat_id
    
    # Сохранение конфигурации
    with open(config_path, 'w') as f:
        yaml.dump(config, f, default_flow_style=False)
    
    # Обновление конфига в приложении
    current_app.config['SOFTDEPLOY_CONFIG'] = config
    
    flash('Настройки Telegram сохранены.', 'success')
    return redirect(url_for('main.settings'))
