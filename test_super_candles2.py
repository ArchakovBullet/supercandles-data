"""Проверка API Super Candles через moexalgo v3"""
import os
from datetime import datetime, timedelta
from moexalgo import Market, Ticker

# Акции: Market('shares')
ticker = Ticker('SBER')
print(f"Ticker создан: {ticker}")

# Ищем методы для Super Candles
all_methods = [m for m in dir(ticker) if not m.startswith('_')]
print(f"\nВсе публичные методы ({len(all_methods)}):")
for m in all_methods:
    print(f"  - {m}")

# Ищем что-то похожее на super/trade/order
candle_methods = [m for m in all_methods if any(w in m.lower() for w in ['super', 'candle', 'trade', 'order', 'ob'])]
print(f"\nМетоды свечей/статистики: {candle_methods}")

# Пробуем вызвать
dt_from = datetime.now() - timedelta(days=5)
dt_till = datetime.now()

for method_name in candle_methods:
    print(f"\nПробуем: {method_name}")
    try:
        method = getattr(ticker, method_name)
        result = method(start=dt_from.strftime('%Y-%m-%d'), end=dt_till.strftime('%Y-%m-%d'))
        data = list(result) if hasattr(result, '__iter__') else [result]
        print(f"  Записей: {len(data)}")
        if data:
            print(f"  Первая: {data[0]}")
    except Exception as e:
        print(f"  Ошибка: {type(e).__name__}: {e}")
