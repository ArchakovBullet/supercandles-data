"""
SberF — простая стратегия без ML (правила)
FutOI + Force Index + SMA + RSI
Стоп 2% + Безубыток 3%
"""

import backtrader as bt
import sys
from pathlib import Path
from datetime import datetime, timedelta

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import os, pandas as pd, numpy as np
from MOEXPy.MOEXPy import MOEXPy
from FinLabPy.My_Indicators import FutOIIndicator, ForceIndex

TIMEFRAME = 'D1'
TICKER = 'SBERF'
DAYS = 730
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
    return bt.feeds.PandasData(dataname=df.set_index('datetime'))

class SberF(bt.Strategy):
    """
    SberF — простая стратегия на правилах
    
    BUY:  FutOI > 100M, FI(13) > 0, цена > SMA(50), 30 < RSI < 70
    SELL: FutOI < 100M, FI(13) < 0, цена < SMA(50), 30 < RSI < 70
    
    Стоп: 2% | Безубыток: +3%
    """
    
    params = (
        ('stop_loss', 0.02),
        ('breakeven_trigger', 0.03),
        ('futoi_threshold', 100),
    )
    
    def __init__(self):
        self.futoi = FutOIIndicator(self.data, ticker=TICKER, lookback=5)
        self.fi = ForceIndex(self.data)
        self.sma = bt.indicators.SMA(self.data.close, period=50)
        self.rsi = bt.indicators.RSI(self.data.close, period=14)
        
        self.entry_price = None
        self.entry_time = None
        self.entry_signal = None
        self.stop_price = None
        self.breakeven_moved = False
        self.order = None
        self.trades_log = []
    
    def _get_signal(self):
        c = self.data.close[0]
        f = self.futoi.phys_net[0]
        fi = self.fi.fi_ema13[0]
        
        buy_ok = f > self.p.futoi_threshold and fi > 0 and c > self.sma[0] and 30 < self.rsi[0] < 70
        sell_ok = f < self.p.futoi_threshold and fi < 0 and c < self.sma[0] and 30 < self.rsi[0] < 70
        
        if buy_ok and not sell_ok: return 'BUY'
        elif sell_ok and not buy_ok: return 'SELL'
        return None
    
    def next(self):
        current_time = self.data.datetime.datetime()
        
        if self.futoi.phys_net[0] == 0: return
        if self.order: return
        
        # Стоп
        if self.entry_price and self.position:
            c = self.data.close[0]
            if not self.breakeven_moved:
                if self.entry_signal == 'BUY' and c >= self.entry_price * (1 + self.p.breakeven_trigger):
                    self.stop_price = self.entry_price; self.breakeven_moved = True
                elif self.entry_signal == 'SELL' and c <= self.entry_price * (1 - self.p.breakeven_trigger):
                    self.stop_price = self.entry_price; self.breakeven_moved = True
            
            hit = (self.entry_signal == 'BUY' and c <= self.stop_price) or \
                  (self.entry_signal == 'SELL' and c >= self.stop_price)
            if hit:
                self._close('СТОП' if self.breakeven_moved else 'СТОП(-2%)', current_time)
                return
        
        # Сигнал
        signal = self._get_signal()
        if signal is None: return
        
        # Закрытие по сигналу
        if self.position:
            self._close(f'→{signal}', current_time)
        if self.order: return
        
        # Вход
        entry = self.data.close[0]
        size = int(self.broker.get_cash() * 0.95 / entry)
        
        if signal == 'BUY':
            self.order = self.buy(size=size)
            self.stop_price = entry * (1 - self.p.stop_loss)
        else:
            self.order = self.sell(size=size)
            self.stop_price = entry * (1 + self.p.stop_loss)
        
        self.entry_price = entry
        self.entry_time = current_time
        self.entry_signal = signal
        self.breakeven_moved = False
        
        emoji = '🟢' if signal == 'BUY' else '🔴'
        print(f"{emoji} {signal} {current_time.strftime('%Y-%m-%d')} @ {entry:.1f} | SL={self.stop_price:.1f}")
    
    def _close(self, reason, current_time):
        exit_price = self.data.close[0]
        pnl = (exit_price - self.entry_price) * self.position.size
        if self.entry_signal == 'SELL': pnl = -pnl
        pnl_pct = (exit_price / self.entry_price - 1) * 100
        if self.entry_signal == 'SELL': pnl_pct = -pnl_pct
        
        self.trades_log.append({
            'Вход': self.entry_time.strftime('%d.%m.%y'),
            'Вых': current_time.strftime('%d.%m.%y'),
            'Т': self.entry_signal,
            'Вход ₽': f'{self.entry_price:.1f}',
            'Вых ₽': f'{exit_price:.1f}',
            'P/L': f'{pnl:+.0f}',
            '%': f'{pnl_pct:+.1f}',
            'Причина': reason,
        })
        
        emoji = '💰' if pnl > 0 else '📉'
        print(f"{emoji} {reason} {current_time.strftime('%Y-%m-%d')} | "
              f"{self.entry_price:.1f}→{exit_price:.1f} | {pnl:+.0f}₽")
        
        self.order = self.close()
        self.entry_price = None
        self.stop_price = None
        self.breakeven_moved = False
    
    def notify_order(self, order):
        if order.status in [order.Completed]: self.order = None
    
    def stop(self):
        if self.position:
            self._close('КОНЕЦ', self.data.datetime.datetime())
        
        print(f"\n{'='*80}")
        print(f"📊 SberF — РЕЗУЛЬТАТЫ")
        print(f"{'='*80}")
        
        if self.trades_log:
            trades_df = pd.DataFrame(self.trades_log)
            print(trades_df.to_string(index=True))
            
            total = len(self.trades_log)
            wins = sum(1 for t in self.trades_log if float(t['P/L'].replace('+','')) > 0)
            total_pnl = sum(float(t['P/L'].replace('+','')) for t in self.trades_log)
            print(f"\n📈 Сделок: {total} | Прибыльных: {wins} ({wins/total*100:.1f}%) | P/L: {total_pnl:+.0f} ₽")


if __name__ == '__main__':
    cerebro = bt.Cerebro()
    cerebro.adddata(load_data())
    cerebro.addstrategy(SberF)
    cerebro.broker.set_cash(100000.0)
    cerebro.broker.setcommission(commission=0.0005)
    
    print(f"\n🚀 SberF | {TICKER} | {TIMEFRAME}")
    print(f"   FutOI + Force Index + SMA(50) + RSI")
    print(f"   Стоп: 2% | Безубыток: +3%")
    print("=" * 60)
    
    results = cerebro.run()
    final = cerebro.broker.getvalue()
    print(f"\n📊 ИТОГ: {final:,.0f} ₽ | Доходность: {(final/100000-1)*100:.1f}%")
    
    if PLOT:
        cerebro.plot(style='candlestick', barup='green', bardown='red', volume=False)
