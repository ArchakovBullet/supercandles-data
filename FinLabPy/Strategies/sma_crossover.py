from MOEXPy.MOEXPy import MOEXPy
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta

# Загрузка данных
api = MOEXPy()
board, symbol = api.dataname_to_board_symbol("TQBR.SBER")
moex_tf = api.timeframe_to_moex_timeframe('D1')
candles = api.get_candles(board, symbol, datetime.now() - timedelta(days=180), datetime.now(), moex_tf)

# Преобразуем в DataFrame
col_idx = {col: idx for idx, col in enumerate(candles['candles']['columns'])}
df = pd.DataFrame([{
    'date': row[col_idx['begin']],
    'close': float(row[col_idx['close']])
} for row in candles['candles']['data']])
df['date'] = pd.to_datetime(df['date'])

# Расчёт скользящих средних
df['SMA_10'] = df['close'].rolling(10).mean()
df['SMA_20'] = df['close'].rolling(20).mean()

# График
fig = go.Figure()
fig.add_trace(go.Scatter(x=df['date'], y=df['close'], name='Цена'))
fig.add_trace(go.Scatter(x=df['date'], y=df['SMA_10'], name='SMA 10'))
fig.add_trace(go.Scatter(x=df['date'], y=df['SMA_20'], name='SMA 20'))
fig.update_layout(title='Сбербанк — SMA Crossover', template='plotly_dark')
fig.show()