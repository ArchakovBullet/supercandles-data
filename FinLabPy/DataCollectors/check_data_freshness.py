"""Проверка свежести данных и уведомление в VK при проблемах"""
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
import sys, os, random
sys.path.insert(0, '/root/finlab')
import vk_api
from vk_api import VkApi

DATA = Path('/root/finlab/data')
MAX_AGE_DAYS = 3
today = datetime.now().date()

# VK настройки
VK_TOKEN = os.getenv('VK_TOKEN', '')
GROUP_ID = int(os.getenv('VK_GROUP_ID', '0'))

def send_vk_message(msg):
    if not VK_TOKEN or not GROUP_ID:
        print("VK не настроен")
        return
    try:
        vk_session = VkApi(token=VK_TOKEN)
        vk = vk_session.get_api()
        vk.messages.send(
            peer_id=GROUP_ID,
            message=msg,
            random_id=random.randint(1, 2**31 - 1)
        )
    except Exception as e:
        print(f'Ошибка VK: {e}')

problems = []

# Проверка FutOI
for f in sorted((DATA / 'futoi').glob('*_futoi.parquet')):
    ticker = f.stem.replace('_futoi', '')
    try:
        df = pd.read_parquet(f)
        if 'tradedate' in df.columns and len(df) > 0:
            last_date = pd.to_datetime(df['tradedate'].max()).date()
            age = (today - last_date).days
            if age > MAX_AGE_DAYS:
                problems.append(f'🔴 {ticker}: FutOI не обновлялся {age} дней (последняя: {last_date})')
    except:
        problems.append(f'❌ {ticker}: ошибка чтения FutOI')

# Проверка свечей
for f in sorted((DATA / 'candles').glob('*_D1.parquet'))[:20]:
    ticker = f.stem.replace('_D1', '')
    try:
        df = pd.read_parquet(f)
        if 'begin' in df.columns and len(df) > 0:
            last_date = pd.to_datetime(df['begin'].max()).date()
            age = (today - last_date).days
            if age > MAX_AGE_DAYS:
                problems.append(f'🟡 {ticker}: свечи не обновлялись {age} дней')
    except:
        pass

if problems:
    msg = f'⚠️ Проблемы со свежестью данных ({today}):\n' + '\n'.join(problems[:10])
    if len(problems) > 10:
        msg += f'\n... и ещё {len(problems)-10} проблем'
    print(msg)
    send_vk_message(msg)
else:
    print(f'✅ Все данные актуальны ({today})')
