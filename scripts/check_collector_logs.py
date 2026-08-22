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

def check_recent_logs():
    """Проверить логи за последние 6 часов на ошибки."""
    now = datetime.now()
    cutoff = now - timedelta(hours=6)
    problems = []
    
    for log_file in LOGS_DIR.glob('*.log'):
        try:
            mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
            if mtime < cutoff:
                continue
            
            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
                # Проверяем последние 100 строк
                for line in lines[-100:]:
                    for pattern in ERROR_PATTERNS:
                        if re.search(pattern, line, re.IGNORECASE):
                            # Не дублируем одинаковые ошибки из одного файла
                            problems.append(f"  📄 {log_file.name}: {line.strip()[:150]}")
                            break
        except:
            pass
    
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
