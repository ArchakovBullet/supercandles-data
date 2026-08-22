#!/usr/bin/env python3
"""Проверка логов сборщиков на ошибки и уведомление в VK."""
import re
from pathlib import Path
from datetime import datetime, timedelta
import sys
import os

sys.path.insert(0, '/root/finlab')
from dotenv import load_dotenv
load_dotenv('/root/finlab/.env')

import vk_api

LOGS_DIR = Path('/root/finlab/logs')
STATE_FILE = Path('/root/finlab/logs/collector_errors_state.json')
TOKEN = os.getenv('VK_TOKEN', '')
GROUP_ID = int(os.getenv('VK_GROUP_ID', '0'))

# Ключевые слова для поиска ошибок
ERROR_PATTERNS = [
    r'ERROR',
    r'ОШИБКА',
    r'Traceback',
    r'SSLCertVerificationError',
    r'ConnectionError',
    r'TimeoutError',
    r'403',
    r'404',
    r'500',
    r'401',
]

def load_state():
    """Загрузить предыдущее состояние ошибок."""
    import json
    if STATE_FILE.exists():
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_state(state):
    """Сохранить состояние ошибок."""
    import json
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def check_recent_logs():
    """Проверить логи за последние 2 часа на новые ошибки."""
    now = datetime.now()
    cutoff = now - timedelta(hours=2)
    state = load_state()
    problems = []
    new_errors = []
    
    for log_file in LOGS_DIR.glob('*.log'):
        # Пропускаем собственный лог
        if log_file.name == 'collector_logs_check.log':
            continue
        try:
            mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
            if mtime < cutoff:
                continue
            
            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
                # Проверяем последние 50 строк
                for line in lines[-50:]:
                    for pattern in ERROR_PATTERNS:
                        if re.search(pattern, line, re.IGNORECASE):
                            # Создаём ключ для дедупликации
                            error_key = f"{log_file.name}:{line.strip()[:80]}"
                            if error_key not in state:
                                problems.append(f"  📄 {log_file.name}: {line.strip()[:150]}")
                                new_errors.append(error_key)
                            break
        except:
            pass
    
    # Обновляем state
    for key in new_errors:
        state[key] = now.strftime('%Y-%m-%d %H:%M:%S')
    # Очищаем state от ошибок старше 24 часов
    state = {k: v for k, v in state.items() if (now - datetime.strptime(v, '%Y-%m-%d %H:%M:%S')).days < 1}
    save_state(state)
    
    return problems

def send_vk_message(msg):
    """Отправить сообщение в VK."""
    if not TOKEN:
        print("VK не настроен")
        return
    try:
        vk_session = vk_api.VkApi(token=TOKEN)
        vk = vk_session.get_api()
        vk.messages.send(
            peer_id=GROUP_ID,
            message=msg,
            random_id=int(datetime.now().timestamp() * 1000)
        )
        print("✅ VK-уведомление отправлено")
    except Exception as e:
        print(f"❌ Ошибка VK: {e}")

if __name__ == '__main__':
    problems = check_recent_logs()
    if problems:
        msg = f"⚠️ Обнаружены ошибки в логах сборщиков ({datetime.now().strftime('%d.%m %H:%M')}):\n"
        msg += "\n".join(problems[:10])
        print(msg)
        send_vk_message(msg)
    else:
        print(f"✅ Ошибок в логах не обнаружено ({datetime.now().strftime('%d.%m %H:%M')})")
