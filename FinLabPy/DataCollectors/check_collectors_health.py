"""
Проверка здоровья всех сборщиков.
Если сборщик не отработал за сегодня — отправляет уведомление в VK.
"""
import os
import sys
from pathlib import Path
from datetime import datetime
import random

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from FinLabPy.Utils import setup_logger

logger = setup_logger('collectors_health')

# ========== КОНФИГ ==========
TOKEN = "vk1.a.SlI9YR5W8dTnTYhVLlhNxXEmgDo6rImtWM1jEIpsZKb9KR8EB_x325YDm_Piu1QZffsffqKethgXWlBH3G0e_6h9DUmZEVzbCmXajTm3jW33hE1F49dUOVtjHGRLYN_5pYOnLN0ZiFpdu_DVVqPHLfShNWDBN1prFS7Yf1ec-PE75C_hhs5Mo7SANbnE_uWzA3dGP3_l3So8HfcUVW3f8A"
ADMIN_PEER_ID = 497763452
LOGS_DIR = Path('/root/finlab/logs')
DATA_DIR = Path('/root/finlab/data')

# Сборщики и их индикаторы
COLLECTORS = {
    'FutOI': {
        'log_pattern': 'futoi_collect_cron.log',
        'data_path': DATA_DIR / 'futoi',
        'critical': True
    },
    'HI2': {
        'log_pattern': 'hi2_collect_cron.log',
        'data_path': DATA_DIR / 'hi2',
        'critical': True
    },
    'Funding': {
        'log_pattern': 'funding_collect_cron.log',
        'data_path': DATA_DIR / 'funding' / 'funding.parquet',
        'critical': False
    },
    'Super Candles': {
        'log_pattern': 'supercandles_collect_cron.log',
        'data_path': DATA_DIR / 'supercandles',
        'critical': False
    },
    'Super Candles H4': {
        'log_pattern': 'supercandles_h4_aggregate_cron.log',
        'data_path': DATA_DIR / 'supercandles_h4',
        'critical': False
    },
    'TradeStats': {
        'log_pattern': 'tradestats_collect_cron.log',
        'data_path': DATA_DIR / 'tradestats',
        'critical': False
    },
    'Candles': {
        'log_pattern': 'candles_collect_cron.log',
        'data_path': DATA_DIR / 'candles',
        'critical': True
    }
}

def check_collector(name, config):
    """Проверяет, отработал ли сборщик: смотрит дату изменения файлов данных"""
    from datetime import timedelta
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)
    
    data_path = config['data_path']
    
    # Получаем самую свежую дату изменения файла
    latest_mtime = None
    if data_path.is_dir():
        files = list(data_path.glob("*.parquet"))
        if files:
            latest_mtime = max(f.stat().st_mtime for f in files)
        else:
            return False, "нет файлов данных"
    elif data_path.exists():
        latest_mtime = data_path.stat().st_mtime
    else:
        return False, "файл данных не найден"
    
    if latest_mtime is None:
        return False, "не удалось определить дату"
    
    latest_date = datetime.fromtimestamp(latest_mtime).date()
    
    # Проверяем, что данные обновлены сегодня или вчера
    if latest_date >= yesterday:
        return True, f"OK (последнее обновление: {latest_date})"
    else:
        return False, f"нет обновлений с {latest_date} (сегодня: {today}, вчера: {yesterday})"

def send_vk_message(message):
    """Отправляет сообщение в VK"""
    import requests
    url = "https://api.vk.com/method/messages.send"
    params = {
        "access_token": TOKEN,
        "peer_id": ADMIN_PEER_ID,
        "message": message,
        "random_id": random.randint(1, 2**31 - 1),
        "v": "5.131"
    }
    try:
        requests.post(url, params=params)
    except:
        pass

def check_memory():
    """Проверяет использование памяти и диска"""
    import psutil
    warnings = []
    
    # RAM
    ram = psutil.virtual_memory()
    ram_pct = ram.percent
    ram_used_gb = ram.used / (1024**3)
    ram_total_gb = ram.total / (1024**3)
    
    # Диск
    disk = psutil.disk_usage('/')
    disk_pct = disk.percent
    disk_free_gb = disk.free / (1024**3)
    
    print(f"RAM: {ram_pct:.1f}% ({ram_used_gb:.1f}/{ram_total_gb:.1f} GB)")
    print(f"Диск: {disk_pct:.1f}% (свободно {disk_free_gb:.1f} GB)")
    
    if ram_pct > 85:
        warnings.append(f"🔴 RAM перегружена: {ram_pct:.1f}%")
    elif ram_pct > 75:
        warnings.append(f"🟡 RAM высокая: {ram_pct:.1f}%")
    
    if disk_pct > 85:
        warnings.append(f"🔴 Диск заполнен: {disk_pct:.1f}%")
    elif disk_pct > 75:
        warnings.append(f"🟡 Диск заполнен: {disk_pct:.1f}%")
    
    return warnings

def main():
    print("=" * 60)
    print(f"ПРОВЕРКА ЗДОРОВЬЯ СБОРЩИКОВ | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    problems = []
    
    # Проверяем память
    print("")
    print("--- ПАМЯТЬ ---")
    mem_warnings = check_memory()
    if mem_warnings:
        problems.extend(mem_warnings)
    print("")
    
    for name, config in COLLECTORS.items():
        ok, msg = check_collector(name, config)
        status = "✅" if ok else "❌"
        print(f"{status} {name}: {msg}")
        
        if not ok:
            problems.append(f"❌ {name}: {msg}")
    
    if problems:
        alert = "⚠️ ПРОБЛЕМЫ СО СБОРЩИКАМИ:\n\n" + "\n".join(problems)
        send_vk_message(alert)
        print("Уведомление отправлено в VK")
    else:
        print("Все сборщики в порядке")

if __name__ == '__main__':
    main()





