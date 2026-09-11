"""
SBERF ML Screener v1.0
ML фильтр + байесовская оптимизация через scikit-optimize
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
from FinLabPy.My_Indicators.futoi_ml_filter import FutOIMLFilter

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
    print(f"   {TICKER}: {len(df)} баров")
    return bt.feeds.PandasData(dataname=df.set_index('datetime'))

class SBERF_ML_Strategy(bt.Strategy):
    """
    SBERF стратегия с ML-фильтром
    
    BUY: FutOI > порог, FI > 0, цена > SMA, RSI 30-70, ML > 55%
    SELL: обратные условия
    """
    
    params = (
        ('stop_loss', 0.02),
        ('breakeven_trigger', 0.03),
        ('futoi_threshold', 30),     # Оптимальный порог для SBERF
        ('min_probability', 0.55),
    )
    
    def __init__(self):
        self.futoi = FutOIIndicator(self.data, ticker=TICKER, lookback=5)
        self.fi = ForceIndex(self.data)
        self.sma = bt.indicators.SMA(self.data.close, period=50)
        self.rsi = bt.indicators.RSI(self.data.close, period=14)
        self.ml_filter = FutOIMLFilter()
        
        self.entry_price = None
        self.entry_time = None
        self.entry_signal = None
        self.entry_probability = None
        self.stop_price = None
        self.breakeven_moved = False
        self.order = None
        self.trades_log = []
        self.ml_ready = False
        self.signal_count = 0
        self.ml_skip_count = 0
    
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
    
    def _get_signal(self):
        c = self.data.close[0]
        
        buy_ok = (self.futoi.phys_net[0] > self.p.futoi_threshold and
                  self.fi.fi_ema13[0] > 0 and
                  c > self.sma[0] and
                  30 < self.rsi[0] < 70)
        
        sell_ok = (self.futoi.phys_net[0] < self.p.futoi_threshold and
                   self.fi.fi_ema13[0] < 0 and
                   c < self.sma[0] and
                   30 < self.rsi[0] < 70)
        
        if buy_ok and not sell_ok:
            return 'BUY'
        elif sell_ok and not buy_ok:
            return 'SELL'
        return None
    
    def next(self):
        current_time = self.data.datetime.datetime()
        bar_num = len(self.data)
        
        # Обучаем ML на 300 барах
        if not self.ml_ready and bar_num >= 300:
            df = self._get_ml_features()
            valid_data = df.iloc[:bar_num]
            print(f"\n   🔧 Обучение ML на {len(valid_data)} строках...")
            acc = self.ml_filter.train(valid_data, forward_days=1)
            self.ml_ready = True
            if acc:
                print(f"   🤖 ML готов! Точность: {acc:.1%}")
        
        if self.futoi.phys_net[0] == 0:
            return
        if self.order:
            return
        
        # Проверка стопа
        if self.entry_price and self.position:
            current = self.data.close[0]
            
            if not self.breakeven_moved:
                if self.entry_signal == 'BUY' and current >= self.entry_price * (1 + self.p.breakeven_trigger):
                    self.stop_price = self.entry_price
                    self.breakeven_moved = True
                    print(f"   🔒 Безубыток! Стоп={self.stop_price:.1f}")
                elif self.entry_signal == 'SELL' and current <= self.entry_price * (1 - self.p.breakeven_trigger):
                    self.stop_price = self.entry_price
                    self.breakeven_moved = True
                    print(f"   🔒 Безубыток! Стоп={self.stop_price:.1f}")
            
            hit = (self.entry_signal == 'BUY' and current <= self.stop_price) or \
                  (self.entry_signal == 'SELL' and current >= self.stop_price)
            
            if hit:
                self._close('СТОП(безуб)' if self.breakeven_moved else 'СТОП(-2%)', current_time)
                return
        
        # Сигнал
        signal = self._get_signal()
        if signal is None:
            return
        
        self.signal_count += 1
        
        # ML фильтр
        if self.ml_ready:
            df = self._get_ml_features()
            valid_data = df.iloc[:bar_num]
            should_enter, proba, direction = self.ml_filter.should_enter(
                valid_data, min_probability=self.p.min_probability
            )
            
            if not should_enter or direction != signal:
                self.ml_skip_count += 1
                return
        else:
            proba = 0.5
        
        # Закрываем старую позицию
        if self.position:
            self._close(f'→{signal}', current_time)
        
        if self.order:
            return
        
        # Открываем новую
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
        self.entry_probability = proba
        self.breakeven_moved = False
        
        emoji = '🟢' if signal == 'BUY' else '🔴'
        print(f"{emoji} {signal} {current_time.strftime('%Y-%m-%d')} @ {entry:.1f} | "
              f"SL={self.stop_price:.1f} | FI={self.fi.fi_ema13[0]:.0f} | ML:{proba:.0%}")
    
    def _close(self, reason, current_time):
        exit_price = self.data.close[0]
        pnl = (exit_price - self.entry_price) * self.position.size
        if self.entry_signal == 'SELL':
            pnl = -pnl
        pnl_pct = (exit_price / self.entry_price - 1) * 100
        if self.entry_signal == 'SELL':
            pnl_pct = -pnl_pct
        
        self.trades_log.append({
            'Вход': self.entry_time.strftime('%d.%m.%y'),
            'Вых': current_time.strftime('%d.%m.%y'),
            'Т': self.entry_signal,
            'Вход ₽': f'{self.entry_price:.1f}',
            'Вых ₽': f'{exit_price:.1f}',
            'P/L': f'{pnl:+.0f}',
            '%': f'{pnl_pct:+.1f}',
            'Причина': reason,
            'ML': f'{self.entry_probability:.0%}' if self.entry_probability else '-',
        })
        
        emoji = '💰' if pnl > 0 else '📉'
        print(f"{emoji} {reason} {current_time.strftime('%Y-%m-%d')} | "
              f"{self.entry_price:.1f}→{exit_price:.1f} | {pnl:+.0f}₽")
        
        self.order = self.close()
        self.entry_price = None
        self.stop_price = None
        self.breakeven_moved = False
    
    def notify_order(self, order):
        if order.status in [order.Completed]:
            self.order = None
    
    def stop(self):
        if self.position:
            self._close('КОНЕЦ', self.data.datetime.datetime())
        
        print(f"\n{'='*80}")
        print(f"📊 SBERF ML SCREENER — РЕЗУЛЬТАТЫ")
        print(f"{'='*80}")
        print(f"   Сигналов: {self.signal_count} | Пропущено ML: {self.ml_skip_count}")
        print(f"   Сделок: {len(self.trades_log)}")
        
        if self.trades_log:
            print(f"\n📊 ЖУРНАЛ СДЕЛОК")
            print(f"{'='*80}")
            print(pd.DataFrame(self.trades_log).to_string(index=True))
            
            total = len(self.trades_log)
            wins = sum(1 for t in self.trades_log if float(t['P/L'].replace('+','')) > 0)
            total_pnl = sum(float(t['P/L'].replace('+','')) for t in self.trades_log)
            print(f"\n📈 Сделок: {total} | Прибыльных: {wins} ({wins/total*100:.1f}%) | P/L: {total_pnl:+.0f} ₽")


if __name__ == '__main__':
    cerebro = bt.Cerebro()
    cerebro.adddata(load_data())
    cerebro.addstrategy(SBERF_ML_Strategy)
    cerebro.broker.set_cash(100000.0)
    cerebro.broker.setcommission(commission=0.0005)
    
    print(f"\n🚀 SBERF ML SCREENER v1.0 | {TICKER} | {TIMEFRAME}")
    print(f"   FutOI порог: 30M | ML фильтр: 55% | Стоп: 2% | Безубыток: 3%")
    print("=" * 60)
    
    results = cerebro.run()
    final = cerebro.broker.getvalue()
    print(f"\n📊 ИТОГ: {final:,.0f} ₽ | Доходность: {(final/100000-1)*100:.1f}%")
    
    if PLOT:
        cerebro.plot(style='candlestick', barup='green', bardown='red', volume=False)
