"""
Проверка здоровья всех сборщиков.
Если сборщик не отработал за сегодня — отправляет уведомление в VK.
"""
import os
import sys
from pathlib import Path
from datetime import datetime
import random

project_root = Path('/root/finlab/FinLabPy')
sys.path.insert(0, str(project_root))

from FinLabPy.Utils import setup_logger

logger = setup_logger('collectors_health')

# ========== КОНФИГ ==========
TOKEN = "vk1.a.SlI9YR5W8dTnTYhVLlhNxXEmgDo6rImtWM1jEIpsZKb9KR8EB_x325YDm_Piu1QZffsffqKethgXWlBH3G0e_6h9DUmZEVzbCmXajTm3jW33hE1F49dUOVtjHGRLYN_5pYOnLN0ZiFpdu_DVVqPHLfShNWDBN1prFS7Yf1ec-PE75C_hhs5Mo7SANbnE_uWzA3dGP3_l3So8HfcUVW3f8A"
GROUP_ID = 238639379
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
    """Проверяет, отработал ли сборщик за сегодня"""
    today = datetime.now().strftime('%Y-%m-%d')
    log_file = LOGS_DIR / config['log_pattern']
    
    if not log_file.exists():
        return False, "лог-файл не найден"
    
    # Проверяем, есть ли записи за сегодня
    with open(log_file, 'r') as f:
        content = f.read()
        if today not in content:
            return False, f"нет записей за сегодня ({today})"
    
    # Проверяем, есть ли данные
    data_path = config['data_path']
    if data_path.is_dir():
        files = list(data_path.glob("*.parquet"))
        if not files:
            return False, "нет файлов данных"
    elif not data_path.exists():
        return False, "файл данных не найден"
    
    return True, "OK"

def send_vk_message(message):
    """Отправляет сообщение в VK"""
    import requests
    url = "https://api.vk.com/method/messages.send"
    params = {
        "access_token": TOKEN,
        "peer_id": GROUP_ID,
        "message": message,
        "random_id": random.randint(1, 2**31 - 1),
        "v": "5.131"
    }
    try:
        requests.post(url, params=params)
    except:
        pass

def main():
    print("=" * 60)
    print(f"ПРОВЕРКА ЗДОРОВЬЯ СБОРЩИКОВ | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    problems = []
    
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
