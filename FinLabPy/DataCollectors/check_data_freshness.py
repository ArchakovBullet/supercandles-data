"""Проверка свежести данных и уведомление в VK при проблемах"""
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
import sys, os, random
sys.path.insert(0, '/root/finlab')

# Загрузка .env
from dotenv import load_dotenv
load_dotenv('/root/finlab/.env')

import vk_api
from vk_api import VkApi

DATA = Path('/root/finlab/data')
MAX_AGE_DAYS = 3
today = datetime.now().date()

# VK настройки
VK_TOKEN = os.getenv('VK_TOKEN', '')
GROUP_ID = int(os.getenv('VK_GROUP_ID', '0'))

# Дата, с которой HI2 API перестал работать
HI2_API_DISABLED_DATE = datetime(2026, 8, 14).date()

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

# ========== ПРОВЕРКА ОШИБОК В CRON-ЛОГАХ ==========
LOGS_DIR = Path('/root/finlab/logs')
MAX_ERRORS_WARN = 10  # > 10 ошибок — проблема

CRON_LOGS = {
    'FutOI': 'futoi_collect_cron.log',
    'Candles': 'candles_collect_cron.log',
    'HI2': 'hi2_collect_cron.log',
    'SuperCandles': 'supercandles_collect_cron.log',
    'Funding': 'funding_collect_cron.log',
    'TradeStats': 'tradestats_collect_cron.log',
    'MegaAlert': 'mega_alert_cron.log',
    'SectorIndices': 'sector_indices_cron.log',
}

for name, log_file in CRON_LOGS.items():
    log_path = LOGS_DIR / log_file
    if not log_path.exists():
        continue
    try:
        text = log_path.read_text(encoding='utf-8', errors='ignore')
        err_count = text.count('ERROR')
        if err_count > MAX_ERRORS_WARN:
            problems.append(f'🔴 {name}: {err_count} ошибок в {log_file}')
    except Exception:
        pass

# ========== ПРОВЕРКА СВЕЖЕСТИ ==========
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

# Проверка HI2 (API закрыт с 14.08.2026 — уведомляем один раз)
hi2_files = list((DATA / 'hi2').glob('*_hi2.parquet'))
if hi2_files:
    # Проверяем, что последняя дата в HI2 < даты отключения API
    try:
        df_hi2 = pd.read_parquet(DATA / 'hi2_daily.parquet')
        if 'tradedate' in df_hi2.columns and len(df_hi2) > 0:
            last_hi2_date = pd.to_datetime(df_hi2['tradedate'].max()).date()
            if last_hi2_date <= HI2_API_DISABLED_DATE:
                days_since = (today - last_hi2_date).days
                if days_since > MAX_AGE_DAYS:
                    problems.append(f'🟠 HI2: API закрыт с 14.08.2026, данные до {last_hi2_date} (отставание {days_since} дней). Отправлен запрос в поддержку AlgoPack.')
    except:
        problems.append('❌ HI2: ошибка чтения данных')

# Проверка Super Candles
supercandles_dir = DATA / 'supercandles'
if supercandles_dir.exists():
    sc_files = list(supercandles_dir.glob('*.parquet'))
    if sc_files:
        latest_sc = max(f.stat().st_mtime for f in sc_files)
        latest_sc_date = datetime.fromtimestamp(latest_sc).date()
        age_sc = (today - latest_sc_date).days
        if age_sc > MAX_AGE_DAYS:
            problems.append(f'🔴 Super Candles не обновлялись {age_sc} дней')
    else:
        problems.append('❌ Super Candles: нет файлов')

# Проверка Funding
funding_file = DATA / 'funding' / 'funding.parquet'
if funding_file.exists():
    age_funding = (today - datetime.fromtimestamp(funding_file.stat().st_mtime).date()).days
    if age_funding > MAX_AGE_DAYS:
        problems.append(f'🔴 Funding не обновлялся {age_funding} дней')
else:
    problems.append('❌ Funding: файл не найден')

# Проверка TradeStats
tradestats_dir = DATA / 'tradestats'
if tradestats_dir.exists():
    ts_files = list(tradestats_dir.glob('*.parquet'))
    if ts_files:
        latest_ts = max(f.stat().st_mtime for f in ts_files)
        latest_ts_date = datetime.fromtimestamp(latest_ts).date()
        age_ts = (today - latest_ts_date).days
        if age_ts > MAX_AGE_DAYS:
            problems.append(f'🔴 TradeStats не обновлялись {age_ts} дней')
    else:
        problems.append('❌ TradeStats: нет файлов')

# Проверка MegaAlert
mega_alerts_dir = DATA / 'mega_alerts'
if mega_alerts_dir.exists():
    ma_files = list(mega_alerts_dir.glob('*.parquet'))
    if ma_files:
        latest_ma = max(f.stat().st_mtime for f in ma_files)
        latest_ma_date = datetime.fromtimestamp(latest_ma).date()
        age_ma = (today - latest_ma_date).days
        if age_ma > MAX_AGE_DAYS:
            problems.append(f'🔴 MegaAlert не обновлялись {age_ma} дней')
    else:
        problems.append('❌ MegaAlert: нет файлов')
else:
    problems.append('❌ MegaAlert: директория не найдена')

if problems:
    msg = f'⚠️ Проблемы со свежестью данных ({today}):\n' + '\n'.join(problems[:10])
    if len(problems) > 10:
        msg += f'\n... и ещё {len(problems)-10} проблем'
    print(msg)
    send_vk_message(msg)
else:
    print(f'✅ Все данные актуальны ({today})')
