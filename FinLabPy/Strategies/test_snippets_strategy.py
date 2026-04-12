"""
Название стратегии: Название
Автор: Денис
Дата: 11
Версия: 1.0

Описание:
Краткое описание
"""

# ==================== БЛОК ИМПОРТОВ ====================
import backtrader as bt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os, sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from MOEXPy.MOEXPy import MOEXPy

import plotly.graph_objects as go
from plotly.subplots import make_subplots


# ==================== БЛОК КОНФИГУРАЦИИ ====================
class StrategyConfig:
    TICKER = "SBER"
    BOARD = "TQBR"
    TIMEFRAME = "D1"
    
    PARAM_1 = 10
    PARAM_2 = 30
    
    RISK_PER_TRADE = 0.02
    START_CASH = 100000
    
    START_DATE = "2024-01-01"
    END_DATE = "2024-12-31"
    
    COMMISSION = 0.0005


# ==================== БЛОК ЗАГРУЗКИ ДАННЫХ ====================
def load_data(config):
    api = MOEXPy(os.getenv('MOEX_TOKEN'))
    board, symbol = api.dataname_to_board_symbol(f"{config.BOARD}.{config.TICKER}")
    
    dt_from = datetime.strptime(config.START_DATE, "%Y-%m-%d")
    dt_till = datetime.strptime(config.END_DATE, "%Y-%m-%d")
    moex_tf = api.timeframe_to_moex_timeframe(config.TIMEFRAME)
    
    candles = api.get_candles(board, symbol, dt_from, dt_till, moex_tf)
    
    col_idx = {col: idx for idx, col in enumerate(candles['candles']['columns'])}
    df = pd.DataFrame([{
        'datetime': row[col_idx['begin']],
        'open': float(row[col_idx['open']]),
        'high': float(row[col_idx['high']]),
        'low': float(row[col_idx['low']]),
        'close': float(row[col_idx['close']]),
        'volume': float(row[col_idx['volume']])
    } for row in candles['candles']['data']])
    
    df['datetime'] = pd.to_datetime(df['datetime'])
    df.set_index('datetime', inplace=True)
    return df


# ==================== БЛОК СТРАТЕГИИ ====================
class TradingStrategy(bt.Strategy):
    
    params = (
        ('param1', 10),
        ('param2', 30),
    )
    
    def __init__(self):
        # ========== ИНИЦИАЛИЗАЦИЯ ==========
        self.order = None
        
        # Индикаторы
        # self.sma_fast = bt.indicators.SMA(self.data.close, period=self.params.param1)
        
    def next(self):
        # ========== ЛОГИКА НА КАЖДОМ БАРЕ ==========
        if self.order:
            return
        
        if not self.position:
            # ====== БЛОК ВХОДА В ПОЗИЦИЮ ======
            pass
        else:
            # ====== БЛОК ВЫХОДА ИЗ ПОЗИЦИИ ======
            pass
    
    # ==================== БЛОК ОБРАБОТКИ ОРДЕРОВ ====================
    def notify_order(self, order):
        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(f'BUY | Price: {order.executed.price:.2f}')
            else:
                self.log(f'SELL | Price: {order.executed.price:.2f}')
        self.order = None
    
    # ==================== БЛОК ЛОГИРОВАНИЯ ====================
    def log(self, txt):
        dt = self.datas[0].datetime.date(0)
        print(f'{dt} | {txt}')


# ==================== БЛОК ЗАПУСКА ====================
def main():
    print("=" * 50)
    print("ЗАПУСК СТРАТЕГИИ")
    print("=" * 50)
    
    config = StrategyConfig()
    df = load_data(config)
    
    cerebro = bt.Cerebro()
    cerebro.addstrategy(TradingStrategy)
    
    data_feed = bt.feeds.PandasData(dataname=df)
    cerebro.adddata(data_feed)
    
    cerebro.broker.setcash(config.START_CASH)
    cerebro.broker.setcommission(commission=config.COMMISSION)
    
    print(f'Начальный капитал: {cerebro.broker.getvalue():.2f}')
    cerebro.run()
    print(f'Конечный капитал: {cerebro.broker.getvalue():.2f}')
    
    # cerebro.plot(style='candlestick')


if __name__ == "__main__":
    main()