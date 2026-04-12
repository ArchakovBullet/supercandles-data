import plotly.graph_objects as go
import pandas as pd

# Пример данных (потом замените на реальные из MOEXPy)
data = pd.DataFrame({
    'date': ['2024-01-01', '2024-01-02', '2024-01-03', '2024-01-04', '2024-01-05'],
    'open': [100, 102, 101, 105, 108],
    'high': [105, 107, 106, 110, 112],
    'low': [99, 101, 100, 104, 107],
    'close': [102, 104, 105, 109, 110],
    'volume': [1000, 1100, 1200, 1300, 1400]
})

# Создаём свечной график
fig = go.Figure(data=[go.Candlestick(
    x=data['date'],
    open=data['open'],
    high=data['high'],
    low=data['low'],
    close=data['close']
)])

# Добавляем заголовок и подписи
fig.update_layout(
    title='Тестовый график (Сбербанк)',
    xaxis_title='Дата',
    yaxis_title='Цена',
    template='plotly_dark'
)

# Показываем график
fig.show()