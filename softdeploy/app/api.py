"""
SoftDeploy - REST API
"""
from flask import Blueprint, jsonify, request
from flask_login import login_required
from app.models import db, Package, Group, Host, DeployRun, Schedule
from app.tasks import run_deploy_task

api_bp = Blueprint('api', __name__)


@api_bp.route('/status')
def status():
    """Статус системы"""
    return jsonify({
        'status': 'ok',
        'service': 'SoftDeploy',
        'version': '1.0.0'
    })


@api_bp.route('/packages')
@login_required
def get_packages():
    """Список пакетов"""
    packages = Package.query.filter_by(is_active=True).all()
    result = []
    for pkg in packages:
        result.append({
            'id': pkg.id,
            'name': pkg.name,
            'app_name': pkg.app_name,
            'version': pkg.version,
            'filename': pkg.filename,
            'silent_keys': pkg.silent_keys,
            'deploy_to_all': pkg.deploy_to_all,
            'created_at': pkg.created_at.isoformat() if pkg.created_at else None
        })
    return jsonify(result)


@api_bp.route('/deploy', methods=['POST'])
@login_required
def api_deploy():
    """Запуск развёртывания"""
    from flask_login import current_user
    
    data = request.get_json() or {}
    
    package_id = data.get('package_id')
    target_type = data.get('target_type', 'all')
    target_id = data.get('target_id')
    
    if not package_id:
        return jsonify({'error': 'package_id is required'}), 400
    
    package = Package.query.get(package_id)
    if not package:
        return jsonify({'error': 'Package not found'}), 404
    
    # Определение имени цели
    target_name = "Все ПК"
    if target_type == 'group' and target_id:
        group = Group.query.get(target_id)
        target_name = f"Группа: {group.name}" if group else "Группа"
    elif target_type == 'host' and target_id:
        host = Host.query.get(target_id)
        target_name = f"Хост: {host.hostname}" if host else "Хост"
    
    # Создание записи о запуске
    deploy_run = DeployRun(
        package_id=package_id,
        target_type=target_type,
        target_id=int(target_id) if target_id else None,
        target_name=target_name,
        status='pending',
        started_by=current_user.id if hasattr(current_user, 'id') else None
    )
    db.session.add(deploy_run)
    db.session.flush()
    
    # Запуск задачи
    run_deploy_task.delay(deploy_run.id)
    
    return jsonify({
        'status': 'started',
        'deploy_run_id': deploy_run.id,
        'package': package.name,
        'target': target_name
    }), 202


@api_bp.route('/hosts')
@login_required
def get_hosts():
    """Список хостов"""
    hosts = Host.query.filter_by(is_active=True).all()
    result = []
    for host in hosts:
        result.append({
            'id': host.id,
            'hostname': host.hostname,
            'ip_address': host.ip_address,
            'group': host.group.name if host.group else None,
            'is_active': host.is_active
        })
    return jsonify(result)


@api_bp.route('/groups')
@login_required
def get_groups():
    """Список групп"""
    groups = Group.query.filter_by(is_active=True).all()
    result = []
    for group in groups:
        result.append({
            'id': group.id,
            'name': group.name,
            'description': group.description,
            'is_active': group.is_active
        })
    return jsonify(result)


@api_bp.route('/schedules')
@login_required
def get_schedules():
    """Список расписаний"""
    schedules = Schedule.query.all()
    result = []
    for sched in schedules:
        result.append({
            'id': sched.id,
            'name': sched.name,
            'cron_expression': sched.cron_expression,
            'is_active': sched.is_active,
            'last_run': sched.last_run.isoformat() if sched.last_run else None,
            'next_run': sched.next_run.isoformat() if sched.next_run else None
        })
    return jsonify(result)


@api_bp.route('/reports/versions')
@login_required
def get_versions():
    """Отчёт по версиям ПО"""
    hosts = Host.query.filter_by(is_active=True).all()
    result = []
    for host in hosts:
        host_data = {
            'hostname': host.hostname,
            'group': host.group.name if host.group else None,
            'versions': []
        }
        for hv in host.versions:
            host_data['versions'].append({
                'package_name': hv.package.name,
                'installed_version': hv.installed_version,
                'required_version': hv.package.version,
                'status': hv.install_status,
                'last_checked': hv.last_checked.isoformat() if hv.last_checked else None
            })
        result.append(host_data)
    return jsonify(result)
