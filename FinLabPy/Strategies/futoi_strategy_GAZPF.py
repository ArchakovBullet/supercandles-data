"""
Стратегия FutOI v4.4 | GAZPF | M10 | порог 0.0003M | без дублей
"""

import backtrader as bt
import sys
from pathlib import Path
from datetime import datetime, timedelta

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import os, pandas as pd, numpy as np
from MOEXPy.MOEXPy import MOEXPy
from FinLabPy.My_Indicators import FutOIIndicator, FutOISignal
from FinLabPy.My_Indicators.futoi_ml_filter import FutOIMLFilter

TIMEFRAME = 'M10'
TICKER = 'GAZPF'
DAYS = 50
PLOT = 'DISPLAY' in os.environ or os.name == 'nt'

def load_data():
    token = os.getenv('MOEX_TOKEN')
    api = MOEXPy(token=token)
    dt_till = datetime.now()
    dt_from = dt_till - timedelta(days=DAYS)
    tf = api.timeframe_to_moex_timeframe(TIMEFRAME)
    print(f"   Загрузка {TICKER} {TIMEFRAME} за {DAYS} дней...")
    data = api.get_candles('RFUD', TICKER, dt_from, dt_till, tf)
    col_idx = {col: idx for idx, col in enumerate(data['candles']['columns'])}
    candles = []
    for row in data['candles']['data']:
        candles.append({
            'datetime': pd.to_datetime(row[col_idx['begin']]),
            'open': float(row[col_idx['open']]),
            'high': float(row[col_idx['high']]),
            'low': float(row[col_idx['low']]),
            'close': float(row[col_idx['close']]),
            'volume': int(row[col_idx['volume']])
        })
    df = pd.DataFrame(candles).sort_values('datetime')
    print(f"   Баров: {len(df)}")
    df.set_index('datetime', inplace=True)
    data_feed = bt.feeds.PandasData(dataname=df)
    return data_feed


class FutOIStrategyML(bt.Strategy):
    params = (
        ('futoi_threshold', 0.0003),
        ('ml_confidence', 55),
    )

    def __init__(self):
        self.futoi = FutOIIndicator()
        self.signal = FutOISignal(self.futoi)
        self.ml_filter = FutOIMLFilter()
        self.order = None
        self.trades_log = []
        self.bar_count = 0

    def notify_order(self, order):
        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(f'BUY  {order.executed.price:.4f} | size={order.executed.size}')
            else:
                self.log(f'SELL {order.executed.price:.4f} | size={order.executed.size}')
            self.trades_log.append({
                'date': self.data.datetime.datetime(),
                'type': 'BUY' if order.isbuy() else 'SELL',
                'price': order.executed.price,
                'size': order.executed.size,
                'P/L': 0
            })
            self.order = None

    def log(self, txt):
        dt = self.data.datetime.datetime()
        print(f'{dt} | {txt}')

    def next(self):
        self.bar_count += 1
        
        if self.bar_count < 50:
            return
        
        if self.order:
            return
        
        ml_ok, ml_confidence = self.ml_filter.check_signal()
        if not ml_ok:
            return
        
        futoi_signal = self.signal[0]
        
        if futoi_signal == 1 and self.position.size <= 0:
            threshold = self.params.futoi_threshold
            if abs(self.futoi.phys_net[0]) > threshold * 1_000_000:
                self.order = self.buy()
                self.log(f'BUY sig | phys_net={self.futoi.phys_net[0]:.0f} | ml_confidence={ml_confidence:.1%}')
        
        elif futoi_signal == -1 and self.position.size >= 0:
            threshold = self.params.futoi_threshold
            if abs(self.futoi.phys_net[0]) > threshold * 1_000_000:
                self.order = self.sell()
                self.log(f'SELL sig | phys_net={self.futoi.phys_net[0]:.0f} | ml_confidence={ml_confidence:.1%}')

    def stop(self):
        print("\n" + "=" * 80)
        print(f"📊 СТАТИСТИКА ТОРГОВЛИ")
        print("=" * 80)
        print(f"   Всего сигналов FutOI: {self.futoi.signal_count}")
        print(f"   Отклонено ML-фильтром: {self.ml_filter.rejected_count}")
        print(f"   Совершено сделок: {len(self.trades_log)}")
        
        if self.trades_log:
            total = len(self.trades_log)
            wins = sum(1 for t in self.trades_log if float(t['P/L']) > 0)
            total_pnl = sum(float(t['P/L']) for t in self.trades_log)
            win_rate = wins / total * 100 if total > 0 else 0
            
            print(f"\n📈 ИТОГИ ТОРГОВЛИ:")
            print(f"   Сделок: {total}")
            print(f"   Прибыльных: {wins} ({win_rate:.1f}%)")
            print(f"   Общий P/L: {total_pnl:+.2f} ₽")


if __name__ == '__main__':
    cerebro = bt.Cerebro()
    cerebro.adddata(load_data())
    cerebro.addstrategy(FutOIStrategyML)
    cerebro.broker.set_cash(100000.0)
    cerebro.broker.setcommission(commission=0.0005)
    
    print(f"\n🚀 FutOI v4.4 | {TICKER} | {TIMEFRAME} | {DAYS} дней")
    print(f"   Капитал: {cerebro.broker.getvalue():,.0f} ₽")
    print(f"   Параметры: мин. уверенность=55% | порог=0.0003M")
    print("=" * 60)
    
    results = cerebro.run()
    final = cerebro.broker.getvalue()
    print(f"\n📊 ИТОГ: {final:,.0f} ₽ | Доходность: {(final/100000-1)*100:.2f}%")
    
    if PLOT:
        cerebro.plot(style='candlestick', barup='green', bardown='red', volume=False)



