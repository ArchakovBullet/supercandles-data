"""
Сборщик свечей через Tinkoff API для корреляций (BR, RTSI, GAZP)
Сохраняет в Parquet, автоудаление через cleanup_old_data.sh (30 дней)
"""
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import requests

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from FinLabPy.Utils import setup_logger

logger = setup_logger('tinkoff_candles_collector')

# ========== КОНФИГ ==========
TINVEST_TOKEN = os.getenv('TINVEST_TOKEN', '')
if not TINVEST_TOKEN:
    raise ValueError("TINVEST_TOKEN не найден в переменных окружения")

# Инструменты: тикер -> FIGI (пока GAZP точно, BR и RTSI уточним)
TICKERS = {
    'GAZP': 'BBG004730N88',  # Акции Газпрома
    # 'BR': '???',           # Нефть Brent — уточнить FIGI
    # 'RTSI': '???'          # Индекс РТС — уточнить FIGI
}

TIMEFRAMES = {'D1': 'D'}  # Для корреляций достаточно дневных свечей
DATA_DIR = Path('/root/finlab/data/candles')
DATA_DIR.mkdir(parents=True, exist_ok=True)

API_URL = 'https://invest-public-api.tinkoff.ru/rest/tinkoff.public.invest.api.contract.v1.MarketDataService/GetCandles'

def get_candles(figi, tf, days=30):
    """Получить свечи через Tinkoff API"""
    headers = {'Authorization': f'Bearer {TINVEST_TOKEN}'}
    to_date = datetime.now()
    from_date = to_date - timedelta(days=days)
    
    payload = {
        'figi': figi,
        'from': from_date.isoformat(),
        'to': to_date.isoformat(),
        'interval': tf
    }
    
    try:
        resp = requests.post(API_URL, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        
        if 'candles' not in data or len(data['candles']) == 0:
            return None
        
        candles = []
        for c in data['candles']:
            candles.append({
                'open': float(c['open']['units']) + float(c['open']['nano']) / 1e9,
                'close': float(c['close']['units']) + float(c['close']['nano']) / 1e9,
                'high': float(c['high']['units']) + float(c['high']['nano']) / 1e9,
                'low': float(c['low']['units']) + float(c['low']['nano']) / 1e9,
                'volume': int(c['volume']),
                'begin': pd.to_datetime(c['time']),
                'end': pd.to_datetime(c['time'])
            })
        
        df = pd.DataFrame(candles)
        return df
    except Exception as e:
        logger.error(f"Ошибка API: {e}")
        return None

def main():
    print("=" * 60)
    print(f"СБОРЩИК TINKOFF СВЕЧЕЙ | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    total = 0
    
    for ticker, figi in TICKERS.items():
        for tf_name, tf_interval in TIMEFRAMES.items():
            print(f"{ticker} D1...", end=' ')
            
            df = get_candles(figi, tf_interval)
            
            if df is None or len(df) == 0:
                print("нет данных")
                continue
            
            file_path = DATA_DIR / f"{ticker}_D1.parquet"
            
            if file_path.exists():
                existing = pd.read_parquet(file_path)
                combined = pd.concat([existing, df], ignore_index=True)
                combined = combined.drop_duplicates(subset=['begin'])
                combined = combined.sort_values('begin')
                combined.to_parquet(file_path, index=False)
            else:
                df.to_parquet(file_path, index=False)
            
            print(f"+{len(df)} свечей")
            total += len(df)
    
    print("=" * 60)
    print(f"ГОТОВО! Всего новых свечей: {total}")
    print(f"Данные в: {DATA_DIR}")
    print("=" * 60)

if __name__ == '__main__':
    main()
