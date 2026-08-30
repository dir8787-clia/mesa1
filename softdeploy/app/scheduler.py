"""
SoftDeploy - APScheduler Configuration
"""
from datetime import datetime
from apscheduler.triggers.cron import CronTrigger
from app.models import db, Schedule, DeployRun
from app.tasks import run_deploy_task


def init_scheduler(scheduler, app):
    """Инициализация планировщика"""
    # Загрузка существующих расписаний из БД
    with app.app_context():
        schedules = Schedule.query.filter_by(is_active=True).all()
        for schedule in schedules:
            add_scheduled_job(schedule, scheduler)


def parse_cron_expression(cron_expr):
    """Парсинг cron выражения в параметры для APScheduler"""
    parts = cron_expr.strip().split()
    
    if len(parts) == 5:
        minute, hour, day, month, day_of_week = parts
    elif len(parts) == 6:
        minute, hour, day, month, day_of_week, year = parts
    else:
        raise ValueError(f"Invalid cron expression: {cron_expr}")
    
    return {
        'minute': minute,
        'hour': hour,
        'day': day,
        'month': month,
        'day_of_week': day_of_week
    }


def add_scheduled_job(schedule, scheduler=None):
    """Добавление задачи в планировщик"""
    from app import scheduler as default_scheduler
    
    if scheduler is None:
        scheduler = default_scheduler
    
    try:
        cron_params = parse_cron_expression(schedule.cron_expression)
        
        trigger = CronTrigger(
            minute=cron_params['minute'],
            hour=cron_params['hour'],
            day=cron_params['day'],
            month=cron_params['month'],
            day_of_week=cron_params['day_of_week']
        )
        
        job = scheduler.add_job(
            run_scheduled_deploy,
            trigger=trigger,
            args=[schedule.id],
            id=f"schedule_{schedule.id}",
            replace_existing=True,
            misfire_grace_time=300
        )
        
        # Обновление next_run
        schedule.next_run = job.next_run_time
        db.session.commit()
        
        return job.id
        
    except Exception as e:
        print(f"Error adding scheduled job: {e}")
        return None


def remove_scheduled_job(job_id, scheduler=None):
    """Удаление задачи из планировщика"""
    from app import scheduler as default_scheduler
    
    if scheduler is None:
        scheduler = default_scheduler
    
    try:
        scheduler.remove_job(job_id)
    except Exception as e:
        print(f"Error removing job {job_id}: {e}")


def run_scheduled_deploy(schedule_id):
    """Запуск развёртывания по расписанию"""
    from app import create_app
    from flask import current_app
    
    # Создание контекста приложения
    app = create_app()
    
    with app.app_context():
        schedule = Schedule.query.get(schedule_id)
        if not schedule or not schedule.is_active:
            return
        
        # Создание записи о запуске
        deploy_run = DeployRun(
            package_id=schedule.package_id,
            target_type=schedule.target_type,
            target_id=schedule.target_id,
            target_name=schedule.target_name or "По расписанию",
            status='pending',
            started_by=None  # Автоматический запуск
        )
        db.session.add(deploy_run)
        db.session.flush()
        
        # Обновление last_run и next_run
        schedule.last_run = datetime.utcnow()
        job = scheduler.get_job(f"schedule_{schedule.id}")
        if job:
            schedule.next_run = job.next_run_time
        db.session.commit()
        
        # Запуск задачи развёртывания
        run_deploy_task(deploy_run.id)
