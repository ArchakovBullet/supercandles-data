from MOEXPy.MOEXPy import MOEXPy
from datetime import datetime, timedelta
import os
import pandas as pd

# Получаем токен из переменной окружения
token = os.getenv('MOEX_TOKEN')

if not token:
    raise ValueError("❌ Токен MOEX не найден! Установите переменную окружения MOEX_TOKEN")

print('🔑 Инициализация MOEXPy с токеном из переменной окружения...')
api = MOEXPy(token=token)

# Получаем свечи Сбербанка
board, symbol = api.dataname_to_board_symbol('TQBR.SBER')
moex_tf = api.timeframe_to_moex_timeframe('D1')
dt_from = datetime.now() - timedelta(days=7)
dt_till = datetime.now()

candles = api.get_candles(board, symbol, dt_from, dt_till, moex_tf)

# Преобразуем в DataFrame для удобного отображения
col_idx = {col: idx for idx, col in enumerate(candles['candles']['columns'])}
data = []
for row in candles['candles']['data']:
    data.append({
        'Дата': row[col_idx['begin']][:10],  # Только дата без времени
        'Open': float(row[col_idx['open']]),
        'High': float(row[col_idx['high']]),
        'Low': float(row[col_idx['low']]),
        'Close': float(row[col_idx['close']]),
        'Volume': int(row[col_idx['volume']])
    })

df = pd.DataFrame(data)

print(f'\n✅ Получено {len(df)} свечей SBER (TQBR, D1)')
print(f'   Период: {df["Дата"].iloc[0]} → {df["Дата"].iloc[-1]}')

# Выводим таблицу
print('📊 СВЕЧИ SBER:')
print('=' * 70)
print(df.to_string(index=True))
print('=' * 70)

# Дополнительная статистика
print('\n📈 СТАТИСТИКА:')
print(f'   Максимальная цена: {df["High"].max():.2f}')
print(f'   Минимальная цена:  {df["Low"].min():.2f}')
print(f'   Средний объём:     {df["Volume"].mean():.0f}')
print(f'   Изменение за период: {((df["Close"].iloc[-1] / df["Close"].iloc[0] - 1) * 100):.2f}%')