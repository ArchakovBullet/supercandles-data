"""
Тестовая стратегия FutOI v2.4 - с автоотключением графика на сервере
"""

import backtrader as bt
import sys
from pathlib import Path
from datetime import datetime, timedelta

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import os
from MOEXPy.MOEXPy import MOEXPy
from FinLabPy.My_Indicators import FutOIIndicator, FutOISignal
import pandas as pd

# Настройки
TIMEFRAME = 'D1'
TICKER = 'GLDRUBF'
DAYS = 50

# Автоопределение: на сервере график не показываем
PLOT = 'DISPLAY' in os.environ or os.name == 'nt'

def load_data():
    token = os.getenv('MOEX_TOKEN')
    api = MOEXPy(token=token)
    
    dt_till = datetime.now()
    dt_from = dt_till - timedelta(days=DAYS)
    tf = api.timeframe_to_moex_timeframe(TIMEFRAME)
    
    print(f"   Загрузка {TICKER} {TIMEFRAME}...")
    candles = api.get_candles('RFUD', TICKER, dt_from, dt_till, tf)
    
    col_idx = {col: idx for idx, col in enumerate(candles['candles']['columns'])}
    data = []
    for row in candles['candles']['data']:
        data.append({
            'datetime': pd.to_datetime(row[col_idx['begin']]),
            'open': float(row[col_idx['open']]),
            'high': float(row[col_idx['high']]),
            'low': float(row[col_idx['low']]),
            'close': float(row[col_idx['close']]),
            'volume': int(row[col_idx['volume']])
        })
    
    df = pd.DataFrame(data).sort_values('datetime')
    print(f"   Баров: {len(df)}")
    return bt.feeds.PandasData(dataname=df.set_index('datetime'))

class FutOIStrategy(bt.Strategy):
    params = (
        ('stop_loss', 0.008),
        ('take_profit', 0.015),
    )
    
    def __init__(self):
        is_intraday = TIMEFRAME in ('M1', 'M10')
        threshold = 2 if is_intraday else 10
        
        self.futoi = FutOIIndicator(self.data, ticker=TICKER, lookback=5, update_intraday=is_intraday)
        self.signal = FutOISignal(self.data, threshold=threshold)
        self.sma = bt.indicators.SMA(self.data.close, period=20)
        self.entry_price = None
        self.order = None
        
    def next(self):
        if self.futoi.phys_net[0] == 0 and self.futoi.phys_net[-1] == 0:
            return
        if self.order:
            return
        
        if not self.position:
            if self.signal.signal[0] == 1 and self.data.close[0] > self.sma[0]:
                size = self.broker.get_cash() * 0.95 / self.data.close[0]
                self.order = self.buy(size=int(size))
                self.entry_price = self.data.close[0]
                print(f"🟢 BUY  {self.data.datetime.date()} @ {self.data.close[0]:.2f}")
                
            elif self.signal.signal[0] == -1 and self.data.close[0] < self.sma[0]:
                size = self.broker.get_cash() * 0.95 / self.data.close[0]
                self.order = self.sell(size=int(size))
                self.entry_price = self.data.close[0]
                print(f"🔴 SELL {self.data.datetime.date()} @ {self.data.close[0]:.2f}")
        else:
            if self.position.size > 0:
                sl = self.entry_price * (1 - self.p.stop_loss)
                tp = self.entry_price * (1 + self.p.take_profit)
                if self.data.close[0] < sl:
                    self.order = self.close()
                    print(f"🛑 SL {self.data.datetime.date()} @ {self.data.close[0]:.2f}")
                elif self.data.close[0] > tp:
                    self.order = self.close()
                    print(f"🎯 TP {self.data.datetime.date()} @ {self.data.close[0]:.2f}")
            elif self.position.size < 0:
                sl = self.entry_price * (1 + self.p.stop_loss)
                tp = self.entry_price * (1 - self.p.take_profit)
                if self.data.close[0] > sl:
                    self.order = self.close()
                    print(f"🛑 SL {self.data.datetime.date()} @ {self.data.close[0]:.2f}")
                elif self.data.close[0] < tp:
                    self.order = self.close()
                    print(f"🎯 TP {self.data.datetime.date()} @ {self.data.close[0]:.2f}")

if __name__ == '__main__':
    cerebro = bt.Cerebro()
    cerebro.adddata(load_data())
    cerebro.addstrategy(FutOIStrategy)
    cerebro.broker.set_cash(100000.0)
    cerebro.broker.setcommission(commission=0.0005)
    
    print(f"\n🚀 FutOI v2.4 | {TICKER} | {TIMEFRAME}")
    print(f"   Капитал: {cerebro.broker.getvalue():,.0f} ₽")
    print(f"   PLOT: {PLOT}")
    print("=" * 60)
    
    results = cerebro.run()
    final = cerebro.broker.getvalue()
    
    print(f"\n📊 ИТОГ: {final:,.0f} ₽ | Доход: {(final/100000-1)*100:.2f}%")
    
    if PLOT:
        cerebro.plot(style='candlestick', barup='green', bardown='red', volume=False)
    else:
        print("   (график отключен — сервер)")
