import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import backtrader as bt
import os
import sys
import pandas as pd

sys.path.insert(0, r'E:\Python\FinLabProject')
from MOEXPy.MOEXPy import MOEXPy


class MOEXData(bt.feeds.PandasData):
    params = (
        ('datetime', 'datetime'),  # Явно указываем колонку с датой
        ('open', 'Open'),
        ('high', 'High'),
        ('low', 'Low'),
        ('close', 'Close'),
        ('volume', 'Volume'),
        ('openinterest', None),
    )


def load_stock_data(ticker: str, timeframe: str, days: int = 5):
    """Загрузка данных акций с MOEX"""
    token = os.getenv('MOEX_TOKEN')
    if not token:
        raise ValueError("❌ Токен MOEX не найден!")
    
    api = MOEXPy(token=token)
    
    dt_till = datetime.now()
    dt_from = dt_till - timedelta(days=days)
    moex_tf = api.timeframe_to_moex_timeframe(timeframe)
    
    print(f'📊 Запрос акций: board=TQBR, ticker={ticker}')
    
    candles = api.get_candles('TQBR', ticker, dt_from, dt_till, moex_tf)
    
    if not candles or 'candles' not in candles or not candles['candles']['data']:
        raise ValueError(f"❌ Нет данных для акции {ticker}")
    
    col_idx = {col: idx for idx, col in enumerate(candles['candles']['columns'])}
    df = pd.DataFrame([{
        'datetime': pd.to_datetime(row[col_idx['begin']]),
        'Open': float(row[col_idx['open']]),
        'High': float(row[col_idx['high']]),
        'Low': float(row[col_idx['low']]),
        'Close': float(row[col_idx['close']]),
        'Volume': int(float(row[col_idx['volume']])),
    } for row in candles['candles']['data']])
    
    # Сортируем по дате
    df = df.sort_values('datetime')
    
    return df


class LogStockData(bt.Strategy):
    def __init__(self):
        self.logger = logging.getLogger('StockData')

    def next(self):
        dt = self.data.datetime.date(0)
        self.logger.info(f'{dt:%d.%m.%Y} | O:{self.data.open[0]:.2f} H:{self.data.high[0]:.2f} L:{self.data.low[0]:.2f} C:{self.data.close[0]:.2f} V:{int(self.data.volume[0])}')


if __name__ == '__main__':
    ticker = 'SBER'
    
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%d.%m.%Y %H:%M:%S',
        level=logging.INFO,
        handlers=[
            logging.FileHandler('StockData.log', encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    logging.Formatter.converter = lambda *args: datetime.now(tz=ZoneInfo('Europe/Moscow')).timetuple()

    print(f'🔑 Загрузка данных акции {ticker} через Algopack...')
    
    df = load_stock_data(ticker, 'D1', days=5)
    print(f'✅ Загружено {len(df)} свечей')
    print(f'   Период: {df["datetime"].iloc[0].date()} → {df["datetime"].iloc[-1].date()}')
    
    cerebro = bt.Cerebro(stdstats=False)
    data = MOEXData(dataname=df)
    cerebro.adddata(data)
    cerebro.addstrategy(LogStockData)
    
    print('🚀 Запуск стратегии...')
    print('=' * 60)
    cerebro.run()
    print('=' * 60)
    print('✅ Готово! Лог записан в StockData.log')