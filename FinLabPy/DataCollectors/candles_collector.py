import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
import sys

# Добавляем путь к FinLabPy для импорта из MOEXPy
sys.path.insert(0, '/root/finlab/FinLabPy')

from MOEXPy.moexalgo import Ticker

# ========== КОНФИГ ==========
# Три группы инструментов
FUTURES = ['CNYRUBF', 'EURRUBF', 'GAZPF', 'GLDRUBF', 'IMOEXF', 'SBERF', 'USDRUBF']
STOCKS = ['SBER', 'GAZP', 'GMKN', 'LKOH', 'PLZL', 'ROSN', 'TATN', 'VTBR', 'HYDR', 'IRAO', 'YNDX']
CORRELATIONS = ['RTS', 'BRENT']

ALL_TICKERS = FUTURES + STOCKS + CORRELATIONS
TIMEFRAMES = ['M10', 'H1', 'D1']

DATA_DIR = Path('/root/finlab/data/candles')
DATA_DIR.mkdir(parents=True, exist_ok=True)

def get_last_date(ticker, timeframe):
    """Получить последнюю дату из локального файла"""
    file_path = DATA_DIR / f"{ticker}_{timeframe}.parquet"
    if file_path.exists():
        df = pd.read_parquet(file_path)
        if not df.empty:
            return df['begin'].max()
    return None

def collect_candles(ticker, timeframe, start_date):
    """Собрать свечи с MOEX начиная с start_date"""
    print(f"  {ticker} {timeframe}...", end=' ')
    
    t = Ticker(ticker)
    
    try:
        # Если нет истории, берём за 365 дней
        if start_date is None:
            start_date = datetime.now() - timedelta(days=365)
        else:
            # Начинаем со следующей свечи после последней сохранённой
            start_date = start_date + timedelta(minutes=1)
        
        end_date = datetime.now()
        
        # Получаем свечи
        candles = t.candles(start=start_date.strftime('%Y-%m-%d'), end=end_date.strftime('%Y-%m-%d'))
        
        if candles is None or len(candles) == 0:
            print("нет новых данных")
            return 0
        
        # Фильтруем по таймфрейму (M10, H1, D1)
        if timeframe == 'M10':
            # Оставляем свечи с шагом 10 минут
            candles['minute'] = candles['begin'].dt.minute
            candles = candles[candles['minute'] % 10 == 0]
        elif timeframe == 'H1':
            candles = candles[candles['begin'].dt.minute == 0]
        
        new_count = len(candles)
        
        # Сохраняем
        file_path = DATA_DIR / f"{ticker}_{timeframe}.parquet"
        
        if file_path.exists():
            existing = pd.read_parquet(file_path)
            combined = pd.concat([existing, candles], ignore_index=True)
            combined = combined.drop_duplicates(subset=['begin'])
            combined = combined.sort_values('begin')
            combined.to_parquet(file_path, index=False)
        else:
            candles.to_parquet(file_path, index=False)
        
        print(f"+{new_count} свечей")
        return new_count
    
    except Exception as e:
        print(f"ошибка: {e}")
        return 0

def main():
    print("=" * 60)
    print(f"СБОРЩИК СВЕЧЕЙ | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    total = 0
    
    for ticker in ALL_TICKERS:
        print(f"\n{ticker}:")
        
        for tf in TIMEFRAMES:
            last_date = get_last_date(ticker, tf)
            count = collect_candles(ticker, tf, last_date)
            total += count
    
    print("\n" + "=" * 60)
    print(f"ГОТОВО! Всего новых свечей: {total}")
    print(f"Данные в: {DATA_DIR}")
    print("=" * 60)

if __name__ == '__main__':
    main()
