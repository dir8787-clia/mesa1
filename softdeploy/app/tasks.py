"""
SoftDeploy - Background Tasks (Ansible Execution)
"""
import os
import subprocess
import threading
import tempfile
from datetime import datetime
from app.models import db, Package, Host, Group, DeployRun, HostVersion, PackageGroup


class AsyncTask:
    """Класс для асинхронного выполнения задач"""
    
    @staticmethod
    def delay(*args, **kwargs):
        """Запуск функции в отдельном потоке"""
        def wrapper(func):
            thread = threading.Thread(target=func, args=args, kwargs=kwargs)
            thread.daemon = True
            thread.start()
            return thread
        return wrapper


def run_deploy_task(deploy_run_id):
    """Задача развёртывания пакета"""
    deploy_run = DeployRun.query.get(deploy_run_id)
    if not deploy_run:
        return
    
    deploy_run.status = 'running'
    db.session.commit()
    
    package = Package.query.get(deploy_run.package_id)
    if not package:
        deploy_run.status = 'failed'
        deploy_run.error_message = 'Пакет не найден'
        deploy_run.completed_at = datetime.utcnow()
        db.session.commit()
        return
    
    # Получение списка хостов для развёртывания
    hosts = get_target_hosts(deploy_run.target_type, deploy_run.target_id, package.deploy_to_all)
    
    if not hosts:
        deploy_run.status = 'failed'
        deploy_run.error_message = 'Нет хостов для развёртывания'
        deploy_run.completed_at = datetime.utcnow()
        db.session.commit()
        return
    
    # Создание временного файла для лога
    log_filename = f"deploy_{deploy_run_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    log_path = os.path.join('/srv/softdeploy/logs', log_filename)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    
    deploy_run.log_file = log_filename
    db.session.commit()
    
    # Генерация Ansible playbook
    playbook_content = generate_ansible_playbook(package, hosts)
    
    # Генерация inventory файла
    inventory_content = generate_ansible_inventory(hosts)
    
    # Создание временных файлов
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as pb_file:
        pb_file.write(playbook_content)
        playbook_path = pb_file.name
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.ini', delete=False) as inv_file:
        inv_file.write(inventory_content)
        inventory_path = inv_file.name
    
    # Запуск Ansible
    try:
        with open(log_path, 'w') as log_file:
            log_file.write(f"=== Развёртывание {package.name} v{package.version} ===\n")
            log_file.write(f"Время начала: {datetime.now()}\n")
            log_file.write(f"Целей: {len(hosts)}\n\n")
            log_file.flush()
            
            cmd = [
                'ansible-playbook',
                '-i', inventory_path,
                playbook_path,
                '-v'
            ]
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            
            for line in process.stdout:
                log_file.write(line)
                log_file.flush()
            
            process.wait()
            exit_code = process.returncode
            
            log_file.write(f"\n=== Завершено с кодом: {exit_code} ===\n")
            log_file.write(f"Время окончания: {datetime.now()}\n")
        
        # Обновление статуса
        if exit_code == 0:
            deploy_run.status = 'success'
        else:
            deploy_run.status = 'failed'
            deploy_run.error_message = f'Ansible exit code: {exit_code}'
        
        deploy_run.exit_code = exit_code
        deploy_run.completed_at = datetime.utcnow()
        db.session.commit()
        
    except Exception as e:
        deploy_run.status = 'failed'
        deploy_run.error_message = str(e)
        deploy_run.completed_at = datetime.utcnow()
        db.session.commit()
        
        with open(log_path, 'a') as log_file:
            log_file.write(f"\n=== ОШИБКА: {str(e)} ===\n")
    
    finally:
        # Очистка временных файлов
        try:
            os.unlink(playbook_path)
            os.unlink(inventory_path)
        except:
            pass


def get_target_hosts(target_type, target_id, deploy_to_all):
    """Получение списка хостов для развёртывания"""
    hosts = []
    
    if target_type == 'all' or deploy_to_all:
        hosts = Host.query.filter_by(is_active=True).all()
    elif target_type == 'group' and target_id:
        group = Group.query.get(target_id)
        if group:
            hosts = Host.query.filter_by(group_id=group.id, is_active=True).all()
    elif target_type == 'host' and target_id:
        host = Host.query.get(target_id)
        if host and host.is_active:
            hosts = [host]
    
    return hosts


def generate_ansible_playbook(package, hosts):
    """Генерация Ansible playbook для установки ПО"""
    
    # PowerShell скрипт для проверки версии
    check_version_script = f'''
$packageName = "{package.app_name}"
$requiredVersion = "{package.version}"

# Поиск в реестре (32-bit и 64-bit)
$paths = @(
    "HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*",
    "HKLM:\\SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*"
)

$installedVersion = $null
foreach ($path in $paths) {{
    $items = Get-ItemProperty -Path $path -ErrorAction SilentlyContinue
    foreach ($item in $items) {{
        if ($item.DisplayName -eq $packageName) {{
            $installedVersion = $item.DisplayVersion
            break
        }}
    }}
    if ($installedVersion) {{ break }}
}}

if ($installedVersion -eq $requiredVersion) {{
    Write-Host "Версия совпадает: $installedVersion"
    exit 0
}} else {{
    Write-Host "Требуется установка. Установлено: $installedVersion, Требуется: $requiredVersion"
    exit 1
}}
'''
    
    # PowerShell скрипт для установки
    install_script = f'''
$installerPath = "C:\\Windows\\Temp\\{package.filename}"
$silentKeys = "{package.silent_keys}"

try {{
    if ($installerPath.EndsWith(".msi")) {{
        $args = "/i `"$installerPath`" /quiet /norestart $silentKeys"
        Start-Process "msiexec.exe" -ArgumentList $args -Wait
    }} else {{
        $args = "$silentKeys"
        Start-Process $installerPath -ArgumentList $args -Wait
    }}
    
    # Удаление установщика
    Remove-Item $installerPath -Force -ErrorAction SilentlyContinue
    
    Write-Host "Установка завершена успешно"
    exit 0
}} catch {{
    Write-Error $_.Exception.Message
    exit 1
}}
'''
    
    playbook = f'''---
- name: Install {package.name} v{package.version}
  hosts: all
  gather_facts: yes
  vars:
    ansible_user: ${{lookup('env', 'WINRM_USER')}}
    ansible_password: ${{lookup('env', 'WINRM_PASSWORD')}}
    ansible_connection: winrm
    ansible_winrm_transport: ntlm
    ansible_winrm_server_cert_validation: ignore
    
  tasks:
    - name: Check installed version
      ansible.windows.win_shell: |
        {check_version_script}
      register: check_result
      ignore_errors: yes
      changed_when: check_result.rc != 0
      
    - name: Copy installer to target
      ansible.windows.win_copy:
        src: /srv/softdeploy/packages/{package.filename}
        dest: C:\\Windows\\Temp\\{package.filename}
      when: check_result.rc != 0
      
    - name: Run installer
      ansible.windows.win_shell: |
        {install_script}
      when: check_result.rc != 0
      register: install_result
      
    - name: Report result
      debug:
        msg: "Installation completed with rc={{% raw %}}{{{{ install_result.rc }}}}{% endraw %}"
      when: check_result.rc != 0
'''
    
    return playbook


def generate_ansible_inventory(hosts):
    """Генерация Ansible inventory файла"""
    inventory = "[windows]\n"
    for host in hosts:
        if host.ip_address:
            inventory += f"{host.hostname} ansible_host={host.ip_address}\n"
        else:
            inventory += f"{host.hostname}\n"
    return inventory


def check_versions_on_host(host):
    """Проверка версий ПО на конкретном хосте"""
    packages = Package.query.filter_by(is_active=True).all()
    
    # PowerShell скрипт для получения всех установленных программ
    ps_script = '''
Get-ItemProperty HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\* |
  Select-Object DisplayName, DisplayVersion, Publisher, InstallDate |
  Where-Object { $_.DisplayName -ne $null } |
  ConvertTo-Json -Compress

Get-ItemProperty HKLM:\\SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\* |
  Select-Object DisplayName, DisplayVersion, Publisher, InstallDate |
  Where-Object { $_.DisplayName -ne $null } |
  ConvertTo-Json -Compress
'''
    
    # Генерация playbook для проверки версий
    playbook = f'''---
- name: Check software versions on {host.hostname}
  hosts: {host.hostname}
  gather_facts: no
  vars:
    ansible_user: ${{lookup('env', 'WINRM_USER')}}
    ansible_password: ${{lookup('env', 'WINRM_PASSWORD')}}
    ansible_connection: winrm
    ansible_winrm_transport: ntlm
    
  tasks:
    - name: Get installed software
      ansible.windows.win_shell: |
        {ps_script}
      register: installed_software
      
    - name: Save result
      ansible.windows.win_copy:
        content: "{{% raw %}}{{{{ installed_software.stdout }}}}{% endraw %}"
        dest: C:\\Windows\\Temp\\installed_software.json
'''
    
    # Запуск проверки (упрощённая версия)
    # В реальности здесь нужен полноценный запуск Ansible
    pass


def check_all_versions():
    """Проверка версий на всех хостах"""
    hosts = Host.query.filter_by(is_active=True).all()
    for host in hosts:
        check_versions_on_host(host)
