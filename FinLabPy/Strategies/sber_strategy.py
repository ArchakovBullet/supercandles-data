from MOEXPy.MOEXPy import MOEXPy
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta

# Инициализация
api = MOEXPy()

# Загрузка данных по Сбербанку
ticker = "SBER"
board = "TQBR"
dt_from = datetime.now() - timedelta(days=30)
dt_till = datetime.now()
moex_tf = api.timeframe_to_moex_timeframe('D1')

print(f"Загружаем данные по {ticker}...")
candles = api.get_candles(board, ticker, dt_from, dt_till, moex_tf)

# Преобразуем в DataFrame
col_idx = {col: idx for idx, col in enumerate(candles['candles']['columns'])}
data_list = []
for row in candles['candles']['data']:
    data_list.append({
        'date': row[col_idx['begin']],
        'open': float(row[col_idx['open']]),
        'high': float(row[col_idx['high']]),
        'low': float(row[col_idx['low']]),
        'close': float(row[col_idx['close']]),
        'volume': int(row[col_idx['volume']])
    })

df = pd.DataFrame(data_list)
df['date'] = pd.to_datetime(df['date'])

# Визуализация
fig = go.Figure(data=[go.Candlestick(
    x=df['date'],
    open=df['open'],
    high=df['high'],
    low=df['low'],
    close=df['close']
)])

fig.update_layout(title=f'Сбербанк (SBER) — последние 30 дней', template='plotly_dark')
fig.show()

print(f"Загружено {len(df)} дней данных")