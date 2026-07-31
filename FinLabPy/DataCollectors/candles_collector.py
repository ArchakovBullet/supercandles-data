"""
Сборщик свечей через MOEXPy для фьючерсов, акций и индексов
Сохраняет в Parquet по таймфреймам M10, H1, D1
"""
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from MOEXPy.MOEXPy import MOEXPy
from FinLabPy.Utils import setup_logger

logger = setup_logger('candles_collector')

# ========== КОНФИГ ==========
# Инструменты с указанием board
def _load_tickers():
    '''Загрузить тикеры из tickers_config.json'''
    import json
    cfg_path = Path(__file__).parent / 'tickers_config.json'
    if cfg_path.exists():
        with open(cfg_path) as f:
            cfg = json.load(f)
        futures = {}
        for t in cfg.get('futures', []):
            futures[t] = 'RFUD'
        stocks = {}
        for t in cfg.get('stocks', []):
            stocks[t] = 'TQBR'
        return futures, stocks
    # Fallback
    return {'CNYRUBF': 'RFUD', 'SBERF': 'RFUD'}, {'SBER': 'TQBR'}

FUTURES, STOCKS = _load_tickers()

CORRELATIONS = {
    'RTS': 'RFUD',   # Индекс РТС (фьючерс)
    'BRENT': 'RFUD'  # Нефть Brent (фьючерс)
}

ALL_TICKERS = {**FUTURES, **STOCKS, **CORRELATIONS}

# Таймфреймы: MOEX interval
TIMEFRAMES = {
    'M10': 10,
    'H1': 60,
    'D1': 24
}

DATA_DIR = Path('/root/finlab/data/candles')
DATA_DIR.mkdir(parents=True, exist_ok=True)


def get_full_code(short_code):
    import json, requests
    from datetime import datetime
    from pathlib import Path
    try:
        cache_file = Path(__file__).parent / "contract_cache.json"
        cache = {}
        if cache_file.exists():
            with open(cache_file) as f:
                cache = json.load(f)
        today = datetime.now().strftime("%Y-%m-%d")
        if short_code in cache and cache[short_code].get("date") == today:
            return cache[short_code]["code"]
        url = "https://iss.moex.com/iss/engines/futures/markets/forts/securities.json"
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return short_code
        data = r.json()["securities"]
        cols = data["columns"]
        rows = data["data"]
        secid_idx = cols.index("SECID")
        sectype_idx = cols.index("SECTYPE")
        date_idx = cols.index("LASTTRADEDATE")
        active = []
        for row in rows:
            if row[sectype_idx].upper() == short_code.upper():
                if row[date_idx] > today:
                    active.append((row[date_idx], row[secid_idx]))
        if active:
            active.sort()
            full_code = active[0][1]
            cache[short_code] = {"code": full_code, "date": today}
            with open(cache_file, "w") as f:
                json.dump(cache, f)
            return full_code
    except:
        pass
    return short_code
def main():
    print("=" * 60)
    print(f"СБОРЩИК СВЕЧЕЙ | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    moex = MOEXPy()
    total = 0
    
    for ticker, board in ALL_TICKERS.items():
        print(f"\n{ticker} ({board}):")
        
        for tf_name, interval in TIMEFRAMES.items():
            print(f"  {tf_name}...", end=' ')
            
            # Определяем дату начала
            file_path = DATA_DIR / f"{ticker}_{tf_name}.parquet"
            if file_path.exists():
                existing = pd.read_parquet(file_path)
                if not existing.empty:
                    dt_from = pd.to_datetime(existing['begin'].max())
                else:
                    dt_from = datetime.now() - timedelta(days=365)
            else:
                dt_from = datetime.now() - timedelta(days=365)
            
            dt_till = datetime.now()
            
            if dt_from >= dt_till:
                print("нет новых данных")
                continue
            
            try:
                api_ticker = get_full_code(ticker) if board == "RFUD" else ticker
                result = moex.get_candles(board, api_ticker, dt_from, dt_till, interval)
                
                if result is None or 'candles' not in result or len(result['candles']['data']) == 0:
                    print("нет данных")
                    continue
                
                # Преобразуем в DataFrame
                columns = result['candles']['columns']
                data = result['candles']['data']
                df = pd.DataFrame(data, columns=columns)
                
                # Переименовываем колонки
                col_map = {
                    'open': 'open',
                    'close': 'close',
                    'high': 'high',
                    'low': 'low',
                    'value': 'value',
                    'volume': 'volume',
                    'begin': 'begin',
                    'end': 'end'
                }
                df = df.rename(columns=col_map)
                
                # Сохраняем
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
                
            except Exception as e:
                print(f"ошибка: {e}")
    
    print("\n" + "=" * 60)
    print(f"ГОТОВО! Всего новых свечей: {total}")
    print(f"Данные в: {DATA_DIR}")
    print("=" * 60)

if __name__ == '__main__':
    main()


