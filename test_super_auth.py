"""Super Candles с авторизацией через токен Algopack"""
import os
from datetime import datetime, timedelta
from moexalgo import Market, Ticker
from moexalgo.session import Session

token = os.getenv('MOEX_TOKEN')
print(f"Токен: {token[:20]}... (длина {len(token)})")

# Создаём сессию с токеном
session = Session(authorization=f'Bearer {token}')

# Получаем Ticker с сессией
ticker = Ticker('SBER')
ticker._session = session  # Пробуем подменить сессию

# Пробуем tradestats (Super Candles)
print("\nЗапрос tradestats (Super Candles)...")
dt_till = datetime.now()
dt_from = dt_till - timedelta(days=5)

try:
    result = ticker.tradestats(start=dt_from.strftime('%Y-%m-%d'), end=dt_till.strftime('%Y-%m-%d'))
    data = list(result)
    print(f"Записей: {len(data)}")
    if data:
        print(f"Первая запись: {data[0]}")
except Exception as e:
    print(f"Ошибка: {e}")
