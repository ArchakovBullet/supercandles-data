"""
Eternal Futures Screener v1.0
Мульти-инструментальная стратегия для вечных фьючерсов
SBERF | GAZPF | IMOEXF | D1
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

# Настройки
TIMEFRAME = 'D1'
TICKERS = ['SBERF', 'GAZPF', 'IMOEXF']
DAYS = 730  # 2 года
PLOT = 'DISPLAY' in os.environ or os.name == 'nt'

def load_data(ticker):
    token = os.getenv('MOEX_TOKEN')
    api = MOEXPy(token=token)
    dt_till = datetime.now()
    dt_from = dt_till - timedelta(days=DAYS)
    tf = api.timeframe_to_moex_timeframe(TIMEFRAME)
    
    try:
        candles = api.get_candles('RFUD', ticker, dt_from, dt_till, tf)
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
        return df
    except Exception as e:
        print(f"   ⚠️ {ticker}: ошибка загрузки - {str(e)[:50]}")
        return None

class EternalFuturesScreener(bt.Strategy):
    """
    Мульти-инструментальный скринер вечных фьючерсов
    
    Отслеживает одновременно SBERF, GAZPF, IMOEXF
    На каждый инструмент выделяется 33% капитала
    """
    
    params = (
        ('min_probability', 0.55),
        ('futoi_threshold', 100),
        ('stop_loss', 0.02),
        ('breakeven_trigger', 0.03),
    )
    
    def __init__(self):
        self.inds = {}  # Индикаторы для каждого тикера
        
        for i, d in enumerate(self.datas):
            ticker = TICKERS[i]
            self.inds[ticker] = {
                'futoi': FutOIIndicator(d, ticker=ticker, lookback=5),
                'fi': ForceIndex(d),
                'sma20': bt.indicators.SMA(d.close, period=20),
                'rsi': bt.indicators.RSI(d.close, period=14),
            }
        
        self.ml_filter = FutOIMLFilter()
        
        # Позиции
        self.positions_state = {t: {
            'entry_price': None, 'entry_time': None, 'entry_signal': None,
            'stop_price': None, 'breakeven_moved': False, 'last_signal': None
        } for t in TICKERS}
        
        self.order = None
        self.trades_log = []
        self.ml_ready = False
        self.skip_count = 0
        self.capital_per_ticker = 100000 / len(TICKERS)  # 33,333 на тикер
    
    def _get_signal(self, ticker, data, idx):
        """Определение сигнала для конкретного тикера"""
        futoi = self.inds[ticker]['futoi']
        fi = self.inds[ticker]['fi']
        sma = self.inds[ticker]['sma20']
        rsi = self.inds[ticker]['rsi']
        
        buy_ok = (futoi.phys_net[0] > self.p.futoi_threshold and
                  fi.fi_ema13[0] > 0 and
                  data.close[0] > sma[0] and
                  30 < rsi[0] < 70)
        
        sell_ok = (futoi.phys_net[0] < self.p.futoi_threshold and
                   fi.fi_ema13[0] < 0 and
                   data.close[0] < sma[0] and
                   30 < rsi[0] < 70)
        
        if buy_ok and not sell_ok:
            return 'BUY'
        elif sell_ok and not buy_ok:
            return 'SELL'
        return None
    
    def _check_stop(self, ticker, data):
        """Проверка стопа"""
        ps = self.positions_state[ticker]
        if ps['entry_price'] is None:
            return False
        
        current = data.close[0]
        
        if ps['entry_signal'] == 'BUY':
            # Обновление безубытка
            if not ps['breakeven_moved'] and current >= ps['entry_price'] * (1 + self.p.breakeven_trigger):
                ps['stop_price'] = ps['entry_price']
                ps['breakeven_moved'] = True
            
            return current <= ps['stop_price']
        else:
            if not ps['breakeven_moved'] and current <= ps['entry_price'] * (1 - self.p.breakeven_trigger):
                ps['stop_price'] = ps['entry_price']
                ps['breakeven_moved'] = True
            
            return current >= ps['stop_price']
    
    def _get_position_size(self, ticker, data):
        """Размер позиции для тикера"""
        return self.capital_per_ticker * 0.95 / data.close[0]
    
    def next(self):
        bar_num = len(self.data0)
        
        # Обучение ML на первом тикере (SBERF)
        if not self.ml_ready and bar_num >= 400:
            # Собираем данные для ML из первого источника
            ml_df = pd.DataFrame({
                'open': self.data0.open.array,
                'high': self.data0.high.array,
                'low': self.data0.low.array,
                'close': self.data0.close.array,
                'volume': self.data0.volume.array,
                'phys_net': self.inds['SBERF']['futoi'].phys_net.array,
                'phys_change': self.inds['SBERF']['futoi'].phys_change.array,
                'jur_net': self.inds['SBERF']['futoi'].jur_net.array,
            })
            valid_data = ml_df.iloc[:bar_num]
            print(f"\n   🔧 Обучение ML на {len(valid_data)} строках (SBERF)...")
            acc = self.ml_filter.train(valid_data, forward_days=1)
            self.ml_ready = True
            if acc:
                print(f"   🤖 ML готов! Точность: {acc:.1%}")
        
        if self.order:
            return
        
        # Проверяем каждый тикер
        for i, data in enumerate(self.datas):
            ticker = TICKERS[i]
            ps = self.positions_state[ticker]
            futoi = self.inds[ticker]['futoi']
            
            if futoi.phys_net[0] == 0:
                continue
            
            # Проверка стопа
            if ps['entry_price'] is not None and self._check_stop(ticker, data):
                reason = 'СТОП(безуб)' if ps['breakeven_moved'] else 'СТОП(-2%)'
                self._close_position(ticker, data, reason)
            
            # Проверка сигнала
            signal = self._get_signal(ticker, data, i)
            if signal is None or signal == ps['last_signal']:
                continue
            
            # Закрываем старую позицию по сигналу
            if ps['entry_price'] is not None:
                self._close_position(ticker, data, f'→{signal}')
            
            if self.order:
                return
            
            # Открываем новую позицию
            entry = data.close[0]
            size = int(self._get_position_size(ticker, data))
            
            if signal == 'BUY':
                self.order = self.buy(data=data, size=size)
                ps['entry_signal'] = 'BUY'
                ps['stop_price'] = entry * (1 - self.p.stop_loss)
                print(f"🟢 {ticker} BUY  @ {entry:.1f} | SL={ps['stop_price']:.1f}")
            elif signal == 'SELL':
                self.order = self.sell(data=data, size=size)
                ps['entry_signal'] = 'SELL'
                ps['stop_price'] = entry * (1 + self.p.stop_loss)
                print(f"🔴 {ticker} SELL @ {entry:.1f} | SL={ps['stop_price']:.1f}")
            
            ps['entry_price'] = entry
            ps['entry_time'] = self.data0.datetime.datetime()
            ps['breakeven_moved'] = False
            ps['last_signal'] = signal
    
    def _close_position(self, ticker, data, reason):
        ps = self.positions_state[ticker]
        exit_price = data.close[0]
        
        pnl = (exit_price - ps['entry_price']) * self.getposition(data).size
        if ps['entry_signal'] == 'SELL':
            pnl = -pnl
        pnl_pct = (exit_price / ps['entry_price'] - 1) * 100
        if ps['entry_signal'] == 'SELL':
            pnl_pct = -pnl_pct
        
        self.trades_log.append({
            'Тикер': ticker,
            'Вход': ps['entry_time'].strftime('%d.%m.%y'),
            'Выход': self.data0.datetime.datetime().strftime('%d.%m.%y'),
            'Тип': ps['entry_signal'],
            'Вход ₽': f'{ps["entry_price"]:.1f}',
            'Выход ₽': f'{exit_price:.1f}',
            'P/L': f'{pnl:+.0f}',
            '%': f'{pnl_pct:+.1f}',
            'Причина': reason,
        })
        
        emoji = '💰' if pnl > 0 else '📉'
        print(f"{emoji} {ticker} {reason} | {ps['entry_price']:.1f}→{exit_price:.1f} | {pnl:+.0f}₽")
        
        self.order = self.close(data=data)
        ps['entry_price'] = None
        ps['stop_price'] = None
        ps['breakeven_moved'] = False
        ps['last_signal'] = None
    
    def notify_order(self, order):
        if order.status in [order.Completed]:
            self.order = None
    
    def stop(self):
        # Закрываем все открытые позиции
        for i, data in enumerate(self.datas):
            ticker = TICKERS[i]
            if self.positions_state[ticker]['entry_price'] is not None:
                self._close_position(ticker, data, 'КОНЕЦ')
        
        print(f"\n{'='*80}")
        print(f"📊 ETERNAL FUTURES SCREENER — РЕЗУЛЬТАТЫ")
        print(f"{'='*80}")
        
        if self.trades_log:
            trades_df = pd.DataFrame(self.trades_log)
            print(f"\n📊 ЖУРНАЛ СДЕЛОК")
            print(f"{'='*80}")
            print(trades_df.to_string(index=True))
            
            print(f"\n📈 ПО ТИКЕРАМ:")
            for ticker in TICKERS:
                ticker_trades = [t for t in self.trades_log if t['Тикер'] == ticker]
                if ticker_trades:
                    ticker_pnl = sum(float(t['P/L'].replace('+','')) for t in ticker_trades)
                    wins = sum(1 for t in ticker_trades if float(t['P/L'].replace('+','')) > 0)
                    print(f"   {ticker}: {len(ticker_trades)} сд | прибыльных {wins} | P/L {ticker_pnl:+.0f} ₽")
                else:
                    print(f"   {ticker}: сделок не было")
            
            total = len(self.trades_log)
            wins = sum(1 for t in self.trades_log if float(t['P/L'].replace('+','')) > 0)
            total_pnl = sum(float(t['P/L'].replace('+','')) for t in self.trades_log)
            print(f"\n📈 ОБЩИЕ ИТОГИ:")
            print(f"   Сделок: {total} | Прибыльных: {wins} ({wins/total*100:.1f}%)")
            print(f"   Общий P/L: {total_pnl:+.0f} ₽")


if __name__ == '__main__':
    cerebro = bt.Cerebro()
    
    # Загружаем данные для всех тикеров
    for ticker in TICKERS:
        df = load_data(ticker)
        if df is not None:
            data = bt.feeds.PandasData(dataname=df.set_index('datetime'))
            cerebro.adddata(data, name=ticker)
            print(f"   ✅ {ticker}: {len(df)} баров")
    
    cerebro.addstrategy(EternalFuturesScreener)
    cerebro.broker.set_cash(100000.0)
    cerebro.broker.setcommission(commission=0.0005)
    
    print(f"\n🚀 ETERNAL FUTURES SCREENER v1.0")
    print(f"   Тикеры: {', '.join(TICKERS)} | {TIMEFRAME} | 2 года")
    print(f"   Стоп: 2% | Безубыток: +3% | Капитал: 100,000 ₽")
    print("=" * 60)
    
    results = cerebro.run()
    final = cerebro.broker.getvalue()
    print(f"\n📊 ИТОГ: {final:,.0f} ₽ | Доходность: {(final/100000-1)*100:.1f}%")
    
    if PLOT:
        cerebro.plot(style='candlestick', barup='green', bardown='red', volume=False)
