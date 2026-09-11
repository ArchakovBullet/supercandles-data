"""
Стратегия FutOI v4.4 | SBERF | M10 | порог 0.0005M | без дублей
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
TICKER = 'SBERF'
DAYS = 50
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

class FutOIStrategyML(bt.Strategy):
    params = (
        ('stop_loss', 0.005),
        ('take_profit', 0.01),
        ('min_probability', 0.55),
        ('forward_days', 1),
    )
    
    def __init__(self):
        is_intraday = True
        threshold = 0.0005  # Снижен до 0.001M для SBERF
        
        # Только ОДИН индикатор FutOI (не создаем второй в FutOISignal!)
        self.futoi = FutOIIndicator(self.data, ticker=TICKER, lookback=5, update_intraday=is_intraday)
        self.sma = bt.indicators.SMA(self.data.close, period=50)
        self.ml_filter = FutOIMLFilter()
        
        # Сигнал создаем вручную (без дублирования FutOI)
        self.entry_price = None
        self.entry_time = None
        self.entry_signal = None
        self.entry_probability = None
        self.order = None
        self.trades_log = []
        self.ml_ready = False
        self.signal_count = 0
        self.skip_count = 0
    
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
        """Ручной расчет сигнала (без создания второго FutOI)"""
        change = self.futoi.phys_change[0]
        if change > 0.001:
            return 1
        elif change < -0.001:
            return -1
        return 0
    
    def next(self):
        current_time = self.data.datetime.datetime()
        bar_num = len(self.data)
        
        # Обучаем ML на 1500 барах
        if not self.ml_ready and bar_num >= 1500:
            df = self._get_ml_features()
            valid_data = df.iloc[:bar_num]
            print(f"\n   🔧 Обучение ML на {len(valid_data)} строках...")
            acc = self.ml_filter.train(valid_data, forward_days=self.p.forward_days)
            self.ml_ready = True
            if acc:
                print(f"   🤖 ML XGBoost готов! Общая точность: {acc:.1%}")
        
        if self.futoi.phys_net[0] == 0:
            return
        if self.order:
            return
        
        if not self.position:
            raw_signal = self._get_signal()
            
            if raw_signal != 0:
                self.signal_count += 1
                
                if self.ml_ready:
                    df = self._get_ml_features()
                    valid_data = df.iloc[:bar_num]
                    should_enter, proba, direction = self.ml_filter.should_enter(
                        valid_data, 
                        min_probability=self.p.min_probability
                    )
                    
                    if should_enter and direction == ('BUY' if raw_signal == 1 else 'SELL'):
                        if raw_signal == 1 and self.data.close[0] > self.sma[0]:
                            size = self.broker.get_cash() * 0.95 / self.data.close[0]
                            self.order = self.buy(size=int(size))
                            self.entry_price = self.data.close[0]
                            self.entry_time = current_time
                            self.entry_signal = 'BUY'
                            self.entry_probability = proba
                            print(f"🟢 BUY  {current_time.strftime('%d.%m %H:%M')} @ {self.data.close[0]:.4f} | ML: {proba:.0%}")
                            
                        elif raw_signal == -1 and self.data.close[0] < self.sma[0]:
                            size = self.broker.get_cash() * 0.95 / self.data.close[0]
                            self.order = self.sell(size=int(size))
                            self.entry_price = self.data.close[0]
                            self.entry_time = current_time
                            self.entry_signal = 'SELL'
                            self.entry_probability = proba
                            print(f"🔴 SELL {current_time.strftime('%d.%m %H:%M')} @ {self.data.close[0]:.4f} | ML: {proba:.0%}")
                    else:
                        self.skip_count += 1
        else:
            exit_price = self.data.close[0]
            exit_reason = None
            
            if self.position.size > 0:
                sl = self.entry_price * (1 - self.p.stop_loss)
                tp = self.entry_price * (1 + self.p.take_profit)
                if self.data.close[0] < sl:
                    self.order = self.close(); exit_reason = 'СТОП-ЛОСС'
                elif self.data.close[0] > tp:
                    self.order = self.close(); exit_reason = 'ТЕЙК-ПРОФИТ'
            else:
                sl = self.entry_price * (1 + self.p.stop_loss)
                tp = self.entry_price * (1 - self.p.take_profit)
                if self.data.close[0] > sl:
                    self.order = self.close(); exit_reason = 'СТОП-ЛОСС'
                elif self.data.close[0] < tp:
                    self.order = self.close(); exit_reason = 'ТЕЙК-ПРОФИТ'
            
            if exit_reason:
                pnl = (exit_price - self.entry_price) * self.position.size
                if self.entry_signal == 'SELL':
                    pnl = -pnl
                
                self.trades_log.append({
                    'Вход': self.entry_time.strftime('%d.%m %H:%M'),
                    'Выход': current_time.strftime('%d.%m %H:%M'),
                    'Тип': self.entry_signal,
                    'Цена входа': f'{self.entry_price:.4f}',
                    'Цена выхода': f'{exit_price:.4f}',
                    'P/L': f'{pnl:+.2f}',
                    'Причина': exit_reason,
                    'Уверенность': f'{self.entry_probability:.0%}',
                })
                
                emoji = '💰' if pnl > 0 else '📉'
                print(f"{emoji} {exit_reason} {current_time.strftime('%d.%m %H:%M')} | P/L: {pnl:+.2f}")
    
    def notify_order(self, order):
        if order.status in [order.Completed]:
            self.order = None
    
    def stop(self):
        print(f"\n{'='*80}")
        print(f"📊 СТАТИСТИКА ТОРГОВЛИ")
        print(f"{'='*80}")
        print(f"   Всего сигналов FutOI: {self.signal_count}")
        print(f"   Отклонено ML-фильтром: {self.skip_count}")
        print(f"   Совершено сделок: {len(self.trades_log)}")
        
        if self.trades_log:
            print(f"\n📊 ЖУРНАЛ СДЕЛОК")
            print(f"{'='*80}")
            trades_df = pd.DataFrame(self.trades_log)
            print(trades_df.to_string(index=True))
            
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
    print(f"   Параметры: мин. уверенность=55% | порог=0.001M")
    print("=" * 60)
    
    results = cerebro.run()
    final = cerebro.broker.getvalue()
    print(f"\n📊 ИТОГ: {final:,.0f} ₽ | Доходность: {(final/100000-1)*100:.2f}%")
    
    if PLOT:
        cerebro.plot(style='candlestick', barup='green', bardown='red', volume=False)

