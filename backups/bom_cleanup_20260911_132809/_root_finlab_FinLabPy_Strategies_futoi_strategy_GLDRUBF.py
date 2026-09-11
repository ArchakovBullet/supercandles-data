"""
Стратегия v6.3 | GLDRUBF | D1 | 2 года | Стоп + Безубыток | Реверсивная
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
TICKER = 'GLDRUBF'
DAYS = 730
PLOT = 'DISPLAY' in os.environ or os.name == 'nt'

def load_data():
    token = os.getenv('MOEX_TOKEN')
    api = MOEXPy(token=token)
    dt_till = datetime.now()
    dt_from = dt_till - timedelta(days=DAYS)
    tf = api.timeframe_to_moex_timeframe(TIMEFRAME)
    print(f"   Загрузка {TICKER} {TIMEFRAME} за {DAYS} дней...")
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

class FutOIForceStrategy(bt.Strategy):
    """
    Стратегия с начальным стопом и переносом в безубыток
    """
    
    params = (
        ('min_probability', 0.55),
        ('futoi_threshold', 100),
        ('stop_loss', 0.02),          # Начальный стоп 2%
        ('breakeven_trigger', 0.03),  # +3% → стоп на цену входа
    )
    
    def __init__(self):
        self.futoi = FutOIIndicator(self.data, ticker=TICKER, lookback=5)
        self.fi = ForceIndex(self.data)
        self.sma20 = bt.indicators.SMA(self.data.close, period=20)
        self.rsi = bt.indicators.RSI(self.data.close, period=14)
        self.ml_filter = FutOIMLFilter()
        
        # Позиция
        self.entry_price = None
        self.entry_time = None
        self.entry_signal = None
        self.entry_probability = None
        self.stop_price = None       # Текущий стоп
        self.breakeven_moved = False
        
        self.order = None
        self.trades_log = []
        self.ml_ready = False
        self.skip_count = 0
        self.last_signal = None
    
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
        buy_ok = (self.futoi.phys_net[0] > self.p.futoi_threshold and
                  self.fi.fi_ema13[0] > 0 and
                  self.data.close[0] > self.sma20[0] and
                  30 < self.rsi[0] < 70)
        
        sell_ok = (self.futoi.phys_net[0] < self.p.futoi_threshold and
                   self.fi.fi_ema13[0] < 0 and
                   self.data.close[0] < self.sma20[0] and
                   30 < self.rsi[0] < 70)
        
        if buy_ok and not sell_ok:
            return 'BUY'
        elif sell_ok and not buy_ok:
            return 'SELL'
        return None
    
    def _update_stop(self):
        """Обновление стоп-цены"""
        if not self.position:
            return
        
        current = self.data.close[0]
        
        if self.position.size > 0:  # BUY
            if not self.breakeven_moved:
                # Проверяем перенос в безубыток (+3%)
                if current >= self.entry_price * (1 + self.p.breakeven_trigger):
                    self.stop_price = self.entry_price
                    self.breakeven_moved = True
                    print(f"   🔒 Безубыток! Стоп={self.stop_price:.0f}")
        else:  # SELL
            if not self.breakeven_moved:
                # Проверяем перенос в безубыток (-3%)
                if current <= self.entry_price * (1 - self.p.breakeven_trigger):
                    self.stop_price = self.entry_price
                    self.breakeven_moved = True
                    print(f"   🔒 Безубыток! Стоп={self.stop_price:.0f}")
    
    def _check_stop(self):
        """Проверка срабатывания стопа"""
        if not self.position:
            return False
        
        current = self.data.close[0]
        
        if self.position.size > 0:  # BUY
            return current <= self.stop_price
        else:  # SELL
            return current >= self.stop_price
    
    def _close_position(self, reason, current_time):
        """Закрытие позиции с логированием"""
        exit_price = self.data.close[0]
        pnl = (exit_price - self.entry_price) * self.position.size
        if self.entry_signal == 'SELL':
            pnl = -pnl
        pnl_pct = (exit_price / self.entry_price - 1) * 100
        if self.entry_signal == 'SELL':
            pnl_pct = -pnl_pct
        
        self.trades_log.append({
            'Вход': self.entry_time.strftime('%d.%m.%y'),
            'Выход': current_time.strftime('%d.%m.%y'),
            'Тип': self.entry_signal,
            'Цена вх': f'{self.entry_price:.0f}',
            'Цена вых': f'{exit_price:.0f}',
            'P/L': f'{pnl:+.0f}',
            '%': f'{pnl_pct:+.1f}',
            'Причина': reason,
            'ML': f'{self.entry_probability:.0%}' if self.entry_probability else '-',
        })
        
        emoji = '💰' if pnl > 0 else '📉'
        print(f"{emoji} {reason} {current_time.strftime('%Y-%m-%d')} | "
              f"{self.entry_price:.0f}→{exit_price:.0f} | {pnl:+.0f}₽ ({pnl_pct:+.1f}%)")
        
        self.order = self.close()
        self._reset_position()
    
    def _reset_position(self):
        self.entry_price = None
        self.stop_price = None
        self.breakeven_moved = False
        self.last_signal = None
    
    def next(self):
        current_time = self.data.datetime.datetime()
        bar_num = len(self.data)
        
        # Обучение ML
        if not self.ml_ready and bar_num >= 400:
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
        
        # Обновляем стоп и проверяем срабатывание
        if self.position:
            self._update_stop()
            if self._check_stop():
                reason = 'СТОП(безуб)' if self.breakeven_moved else 'СТОП(-2%)'
                self._close_position(reason, current_time)
                return
        
        # Проверяем сигнал
        signal = self._get_signal()
        
        if signal is None or signal == self.last_signal:
            return
        
        # ML фильтр
        if self.ml_ready:
            df = self._get_ml_features()
            valid_data = df.iloc[:bar_num]
            should_enter, proba, direction = self.ml_filter.should_enter(
                valid_data, min_probability=self.p.min_probability
            )
            if not should_enter or direction != signal:
                self.skip_count += 1
                return
        else:
            proba = 0.5
        
        # Закрываем старую позицию по сигналу
        if self.position:
            self._close_position(f'→{signal}', current_time)
        
        # Ждем закрытия старой позиции
        if self.order:
            return
        
        # Открываем новую позицию
        size = self.broker.get_cash() * 0.95 / self.data.close[0]
        entry = self.data.close[0]
        
        if signal == 'BUY':
            self.order = self.buy(size=int(size))
            self.entry_signal = 'BUY'
            self.stop_price = entry * (1 - self.p.stop_loss)  # -2%
            print(f"🟢 BUY  {current_time.strftime('%Y-%m-%d')} @ {entry:.0f} | "
                  f"SL={self.stop_price:.0f} | FutOI={self.futoi.phys_net[0]:.0f}M | ML:{proba:.0%}")
        elif signal == 'SELL':
            self.order = self.sell(size=int(size))
            self.entry_signal = 'SELL'
            self.stop_price = entry * (1 + self.p.stop_loss)  # +2%
            print(f"🔴 SELL {current_time.strftime('%Y-%m-%d')} @ {entry:.0f} | "
                  f"SL={self.stop_price:.0f} | FutOI={self.futoi.phys_net[0]:.0f}M | ML:{proba:.0%}")
        
        self.entry_price = entry
        self.entry_time = current_time
        self.entry_probability = proba
        self.breakeven_moved = False
        self.last_signal = signal
    
    def notify_order(self, order):
        if order.status in [order.Completed]:
            self.order = None
    
    def stop(self):
        if self.position:
            self._close_position('КОНЕЦ', self.data.datetime.datetime())
        
        print(f"\n{'='*80}")
        print(f"📊 СТАТИСТИКА ТОРГОВЛИ")
        print(f"{'='*80}")
        print(f"   Пропущено ML: {self.skip_count}")
        print(f"   Сделок: {len(self.trades_log)}")
        
        if self.trades_log:
            print(f"\n📊 ЖУРНАЛ СДЕЛОК")
            print(f"{'='*80}")
            trades_df = pd.DataFrame(self.trades_log)
            print(trades_df.to_string(index=True))
            
            total = len(self.trades_log)
            wins = sum(1 for t in self.trades_log if float(t['P/L'].replace('+','')) > 0)
            total_pnl = sum(float(t['P/L'].replace('+','')) for t in self.trades_log)
            
            print(f"\n📈 ИТОГИ:")
            print(f"   Сделок: {total} | Прибыльных: {wins} ({wins/total*100:.1f}%)")
            print(f"   Общий P/L: {total_pnl:+.0f} ₽")


if __name__ == '__main__':
    cerebro = bt.Cerebro()
    cerebro.adddata(load_data())
    cerebro.addstrategy(FutOIForceStrategy)
    cerebro.broker.set_cash(100000.0)
    cerebro.broker.setcommission(commission=0.0005)
    
    print(f"\n🚀 v6.3 Стоп+Безубыток | {TICKER} | {TIMEFRAME} | 2 года")
    print(f"   Стоп: 2% | Безубыток при: +3% | Без трейлинга")
    print(f"   Капитал: {cerebro.broker.getvalue():,.0f} ₽")
    print("=" * 60)
    
    results = cerebro.run()
    final = cerebro.broker.getvalue()
    print(f"\n📊 ИТОГ: {final:,.0f} ₽ | Доходность: {(final/100000-1)*100:.1f}%")
    
    if PLOT:
        cerebro.plot(style='candlestick', barup='green', bardown='red', volume=False)
