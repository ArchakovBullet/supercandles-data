"""
Сборщик TradeStats для вертикального профиля объёма (Volume Profile)
Сохраняет агрегированные объёмы по ценовым уровням
"""
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import json

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from MOEXPy.MOEXPy import MOEXPy
from FinLabPy.Utils import setup_logger

logger = setup_logger('tradestats_collector')

# ========== КОНФИГ ==========
# Вечные фьючерсы (те, что уже есть в проекте)
FUTURES = ['CNYRUBF', 'EURRUBF', 'GAZPF', 'GLDRUBF', 'IMOEXF', 'SBERF', 'USDRUBF']

# Акции (для которых есть Super Candles)
STOCKS = ['SBER', 'GAZP', 'GMKN', 'LKOH', 'PLZL', 'ROSN', 'TATN', 'VTBR', 'HYDR', 'IRAO']

DATA_DIR = Path('/root/finlab/data/tradestats')
DATA_DIR.mkdir(parents=True, exist_ok=True)

def collect_tradestats(ticker, board):
    """Собрать TradeStats для одного тикера"""
    print(f"  {ticker} ({board})...", end=' ')
    
    moex = MOEXPy()
    
    # Определяем даты: последние 30 дней
    dt_till = datetime.now()
    dt_from = dt_till - timedelta(days=30)
    
    try:
        result = moex.get_tradestats(ticker, dt_from, dt_till, board)
        
        if result is None or 'data' not in result or len(result['data']) == 0:
            print("нет данных")
            return 0
        
        # Преобразуем в DataFrame
        df = pd.DataFrame(result['data'])
        
        if df.empty:
            print("пустой ответ")
            return 0
        
        # Сохраняем
        file_path = DATA_DIR / f"{ticker}_tradestats.parquet"
        
        if file_path.exists():
            existing = pd.read_parquet(file_path)
            combined = pd.concat([existing, df], ignore_index=True)
            combined = combined.drop_duplicates()
            combined.to_parquet(file_path, index=False)
        else:
            df.to_parquet(file_path, index=False)
        
        print(f"+{len(df)} записей")
        return len(df)
    
    except Exception as e:
        print(f"ошибка: {e}")
        return 0

def main():
    print("=" * 60)
    print(f"СБОРЩИК TRADESTATS | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    total = 0
    
    # Фьючерсы (board='RFUD')
    print("\n=== ФЬЮЧЕРСЫ ===")
    for ticker in FUTURES:
        count = collect_tradestats(ticker, 'RFUD')
        total += count
    
    # Акции (board='TQBR')
    print("\n=== АКЦИИ ===")
    for ticker in STOCKS:
        count = collect_tradestats(ticker, 'TQBR')
        total += count
    
    print("\n" + "=" * 60)
    print(f"ГОТОВО! Всего новых записей: {total}")
    print(f"Данные в: {DATA_DIR}")
    print("=" * 60)

if __name__ == '__main__':
    main()
