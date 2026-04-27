"""
Стратегия FutOI v3.2 ML | GLDRUBF | D1 (исправлено)
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

TIMEFRAME = 'D1'
TICKER = 'GLDRUBF'
DAYS = 50
PLOT = 'DISPLAY' in os.environ or os.name == 'nt'

def load_data():
    token = os.getenv('MOEX_TOKEN')
    api = MOEXPy(token=token)
    dt_till = datetime.now()
    dt_from = dt_till - timedelta(days=DAYS)
    tf = api.timeframe_to_moex_timeframe(TIMEFRAME)
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

class FutOIStrategyML(bt.Strategy):
    params = (
        ('stop_loss', 0.008),
        ('take_profit', 0.015),
        ('min_probability', 0.55),
        ('forward_days', 3),
    )
    
    def __init__(self):
        is_intraday = TIMEFRAME in ('M1', 'M10')
        threshold = 0.005 if is_intraday else 0.01
        
        self.futoi = FutOIIndicator(self.data, ticker=TICKER, lookback=5, update_intraday=is_intraday)
        # 🔧 Передаем ticker в FutOISignal
        self.signal = FutOISignal(self.data, ticker=TICKER, threshold=threshold)
        self.sma = bt.indicators.SMA(self.data.close, period=20)
        
        self.ml_filter = FutOIMLFilter()
        self.entry_price = None
        self.entry_time = None
        self.entry_signal = None
        self.entry_probability = None
        self.order = None
        self.trades_log = []
        self.ml_ready = False
    
    def _get_ml_features(self):
        return pd.DataFrame({
            'open': self.data.open.array,
            'high': self.data.high.array,
            'low': self.data.low.array,
            'close': self.data.close.array,
            'volume': self.data.volume.array,
            'phys_net': self.futoi.phys_net.array,
            'phys_change': self.futoi.phys_change.array,
            'jur_net': self.futoi.jur_net.array,
        })
    
    def next(self):
        current_time = self.data.datetime.datetime()
        bar_num = len(self.data)
        
        if not self.ml_ready and bar_num >= 20:
            df = self._get_ml_features()
            valid_data = df.iloc[:bar_num]
            acc = self.ml_filter.train(valid_data, forward_days=self.p.forward_days)
            self.ml_ready = True
            if acc:
                print(f"   🤖 ML готов! Точность: {acc:.1%}")
        
        if self.futoi.phys_net[0] == 0:
            return
        if self.order:
            return
        
        if not self.position:
            raw_signal = self.signal.signal[0]
            
            if raw_signal != 0 and self.ml_ready:
                df = self._get_ml_features()
                valid_data = df.iloc[:bar_num]
                should_enter, proba, direction = self.ml_filter.should_enter(valid_data, min_probability=self.p.min_probability)
                
                if should_enter:
                    if raw_signal == 1 and direction == 'BUY' and self.data.close[0] > self.sma[0]:
                        size = self.broker.get_cash() * 0.95 / self.data.close[0]
                        self.order = self.buy(size=int(size))
                        self.entry_price = self.data.close[0]
                        self.entry_time = current_time
                        self.entry_signal = 'BUY'
                        self.entry_probability = proba
                        print(f"🟢 BUY  {current_time.strftime('%Y-%m-%d %H:%M')} @ {self.data.close[0]:.2f} | ML: {proba:.1%}")
                        
                    elif raw_signal == -1 and direction == 'SELL' and self.data.close[0] < self.sma[0]:
                        size = self.broker.get_cash() * 0.95 / self.data.close[0]
                        self.order = self.sell(size=int(size))
                        self.entry_price = self.data.close[0]
                        self.entry_time = current_time
                        self.entry_signal = 'SELL'
                        self.entry_probability = proba
                        print(f"🔴 SELL {current_time.strftime('%Y-%m-%d %H:%M')} @ {self.data.close[0]:.2f} | ML: {proba:.1%}")
        else:
            exit_price = self.data.close[0]
            exit_reason = None
            
            if self.position.size > 0:
                sl = self.entry_price * (1 - self.p.stop_loss)
                tp = self.entry_price * (1 + self.p.take_profit)
                if self.data.close[0] < sl:
                    self.order = self.close(); exit_reason = 'SL'
                elif self.data.close[0] > tp:
                    self.order = self.close(); exit_reason = 'TP'
            else:
                sl = self.entry_price * (1 + self.p.stop_loss)
                tp = self.entry_price * (1 - self.p.take_profit)
                if self.data.close[0] > sl:
                    self.order = self.close(); exit_reason = 'SL'
                elif self.data.close[0] < tp:
                    self.order = self.close(); exit_reason = 'TP'
            
            if exit_reason:
                pnl = (exit_price - self.entry_price) * self.position.size
                if self.entry_signal == 'SELL': pnl = -pnl
                self.trades_log.append({
                    'Вход': self.entry_time.strftime('%d.%m %H:%M'),
                    'Выход': current_time.strftime('%d.%m %H:%M'),
                    'Сигнал': self.entry_signal,
                    'Вход ₽': f'{self.entry_price:.2f}',
                    'Выход ₽': f'{exit_price:.2f}',
                    'PnL': f'{pnl:+.2f}',
                    'Причина': exit_reason,
                })
                emoji = '💰' if pnl > 0 else '📉'
                print(f"{emoji} {exit_reason} | PnL: {pnl:+.2f}")
    
    def notify_order(self, order):
        if order.status in [order.Completed]: self.order = None
    
    def stop(self):
        if self.trades_log:
            print(f"\n{'='*80}")
            print(f"📊 ЖУРНАЛ СДЕЛОК")
            print(f"{'='*80}")
            print(pd.DataFrame(self.trades_log).to_string(index=True))

if __name__ == '__main__':
    cerebro = bt.Cerebro()
    cerebro.adddata(load_data())
    cerebro.addstrategy(FutOIStrategyML)
    cerebro.broker.set_cash(100000.0)
    cerebro.broker.setcommission(commission=0.0005)
    print(f"\n🚀 FutOI v3.2 | {TICKER} | {TIMEFRAME}")
    print("=" * 60)
    results = cerebro.run()
    final = cerebro.broker.getvalue()
    print(f"\n📊 ИТОГ: {final:,.0f} ₽ | Доход: {(final/100000-1)*100:.2f}%")
    if PLOT: cerebro.plot(style='candlestick', barup='green', bardown='red', volume=False)
