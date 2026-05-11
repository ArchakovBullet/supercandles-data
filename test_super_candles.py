"""Проверка API Super Candles через moexalgo"""
import os
from moexalgo import Market, Ticker

token = os.getenv('MOEX_TOKEN')

# Пробуем получить Super Candles для SBER
ticker = Ticker('SBER', market=Market.SHARES)
print(f"Ticker: {ticker}")

# Проверяем доступные методы
methods = [m for m in dir(ticker) if 'candle' in m.lower() or 'super' in m.lower()]
print(f"Методы со свечами: {methods}")

# Пробуем tradestats (Super Candles основаны на них)
try:
    from datetime import datetime, timedelta
    dt_till = datetime.now()
    dt_from = dt_till - timedelta(days=5)
    
    print(f"\nЗапрос Super Candles с {dt_from.date()} по {dt_till.date()}...")
    
    # Метод может называться supercandles, super_candles, ohlcsuper и т.д.
    for method_name in ['supercandles', 'super_candles', 'candles', 'tradestats', 'orderstats', 'obstats']:
        if hasattr(ticker, method_name):
            print(f"\nТестируем метод: {method_name}")
            try:
                method = getattr(ticker, method_name)
                result = method(date=dt_from.strftime('%Y-%m-%d'), till_date=dt_till.strftime('%Y-%m-%d'))
                print(f"  Тип результата: {type(result)}")
                if hasattr(result, '__iter__'):
                    data = list(result)
                    print(f"  Записей: {len(data)}")
                    if data:
                        print(f"  Первая запись: {data[0]}")
            except Exception as e:
                print(f"  Ошибка: {e}")
        
except Exception as e:
    print(f"Общая ошибка: {e}")
    import traceback
    traceback.print_exc()
