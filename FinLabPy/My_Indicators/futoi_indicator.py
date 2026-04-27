"""
Индикатор FutOI v2.8 - НОРМАЛИЗОВАННАЯ агрегация (среднее за срез)
"""

import backtrader as bt
import os
from datetime import datetime, timedelta
from collections import defaultdict
from MOEXPy.MOEXPy import MOEXPy


class FutOIIndicator(bt.Indicator):
    """
    Индикатор FutOI v2.8
    
    Нормализация: показывает СРЕДНЮЮ позицию за срез (а не сумму за день).
    Так изменения позиций между днями отражают реальное движение, 
    а не разное количество срезов.
    
    Формула:
        phys_net = (sum(FIZ_long) - sum(FIZ_short)) / n_snapshots / 1_000_000
    """
    
    lines = ('phys_net', 'jur_net', 'phys_change', 'phys_long', 'phys_short')
    
    params = (
        ('ticker', 'GLDRUBF'),
        ('lookback', 5),
        ('update_intraday', False),
    )
    
    plotinfo = dict(
        plot=True,
        subplot=True,
        plotname='FutOI (Физ/Юр лица)',
        plotlines=dict(
            phys_net=dict(color='green', _name='Физ.нетто'),
            jur_net=dict(color='red', _name='Юр.нетто'),
            phys_change=dict(color='blue', _name='Изм.физ', _method='bar'),
            phys_long=dict(color='lime', _name='Физ.лонг', _plotskip=True),
            phys_short=dict(color='pink', _name='Физ.шорт', _plotskip=True),
        )
    )
    
    def __init__(self):
        self.api = None
        self._daily_data = {}
        self._load_futoi_data()
    
    def _init_api(self):
        if self.api is None:
            token = os.getenv('MOEX_TOKEN')
            if token:
                import sys, io
                old_stderr = sys.stderr
                sys.stderr = io.StringIO()
                self.api = MOEXPy(token=token)
                sys.stderr = old_stderr
        return self.api is not None
    
    def _load_futoi_data(self):
        """Загрузка с НОРМАЛИЗАЦИЕЙ — делим сумму на количество срезов"""
        if not self._init_api():
            return
        
        try:
            dt_till = datetime.now()
            dt_from = dt_till - timedelta(days=self.p.lookback + 5)
            
            data = self.api.get_futoi(self.p.ticker, dt_from, dt_till)
            
            if 'futoi' in data and 'data' in data['futoi']:
                cols = data['futoi']['columns']
                rows = data['futoi']['data']
                idx = {c: i for i, c in enumerate(cols)}
                
                # Суммируем все срезы за день
                daily_sum = defaultdict(lambda: {'FIZ_long': 0, 'FIZ_short': 0, 'YUR_long': 0, 'YUR_short': 0})
                daily_count = defaultdict(int)  # Количество срезов за день
                
                for row in rows:
                    date = str(row[idx['tradedate']])[:10]
                    clgroup = row[idx['clgroup']]
                    pos_long = int(row[idx['pos_long']]) if row[idx['pos_long']] else 0
                    pos_short = abs(int(row[idx['pos_short']])) if row[idx['pos_short']] else 0
                    
                    daily_sum[date][f'{clgroup}_long'] += pos_long
                    daily_sum[date][f'{clgroup}_short'] += pos_short
                    daily_count[date] += 1
                
                # НОРМАЛИЗУЕМ: делим на количество срезов
                for date, d in daily_sum.items():
                    n = daily_count[date] / 2 if daily_count[date] > 0 else 1  # /2 т.к. FIZ+YUR
                    
                    self._daily_data[date] = {
                        'phys_net': (d['FIZ_long'] - d['FIZ_short']) / n / 1_000_000,
                        'jur_net': (d['YUR_long'] - d['YUR_short']) / n / 1_000_000,
                        'phys_long': d['FIZ_long'] / n / 1_000_000,
                        'phys_short': d['FIZ_short'] / n / 1_000_000,
                    }
                
                print(f"   FutOI v2.8: {len(daily_sum)} дней (нормализовано)")
                for date in sorted(daily_sum.keys())[-3:]:
                    d = self._daily_data[date]
                    print(f"   {date}: phys_net={d['phys_net']:.3f}M (срезов: {daily_count[date]//2})")
                
        except Exception as e:
            print(f"   ⚠️ FutOI: ошибка - {e}")
    
    def _get_daily_value(self, bar_date):
        date_str = bar_date.strftime('%Y-%m-%d')
        if date_str in self._daily_data:
            return self._daily_data[date_str]
        
        sorted_dates = sorted(self._daily_data.keys())
        for d in reversed(sorted_dates):
            if d <= date_str:
                return self._daily_data[d]
        if sorted_dates:
            return self._daily_data[sorted_dates[0]]
        return None
    
    def _get_intraday_value(self, bar_datetime):
        return self._get_daily_value(bar_datetime)
    
    def next(self):
        bar_dt = self.data.datetime.datetime()
        
        if self.p.update_intraday:
            futoi = self._get_intraday_value(bar_dt)
        else:
            futoi = self._get_daily_value(bar_dt)
        
        if futoi is None:
            futoi = {'phys_net': 0, 'jur_net': 0, 'phys_long': 0, 'phys_short': 0}
        
        prev_net = self.lines.phys_net[-1] if len(self.lines.phys_net) > 1 else 0
        
        self.lines.phys_net[0] = futoi['phys_net']
        self.lines.jur_net[0] = futoi['jur_net']
        self.lines.phys_long[0] = futoi['phys_long']
        self.lines.phys_short[0] = futoi['phys_short']
        
        # Изменение СРЕДНЕЙ позиции
        self.lines.phys_change[0] = futoi['phys_net'] - prev_net if prev_net != 0 else 0


class FutOISignal(bt.Indicator):
    """
    Сигнал на основе ИЗМЕНЕНИЯ средней позиции физиков
    
    Порог для дневного графика: 0.01M (10 тысяч на срез)
    Порог для внутридневного: 0.005M (5 тысяч на срез)
    """
    lines = ('signal',)
    params = (
        ('threshold', 0.01),  # 0.01M = 10 тысяч — порог для дневного графика
    )
    
    plotinfo = dict(
        plot=True,
        subplot=True,
        plotname='FutOI Signal',
        plotlines=dict(signal=dict(_method='bar', color='blue', alpha=0.5))
    )
    
    def __init__(self):
        self.futoi = FutOIIndicator(self.data)
    
    def next(self):
        if self.futoi.phys_change[0] > self.p.threshold:
            self.lines.signal[0] = 1
        elif self.futoi.phys_change[0] < -self.p.threshold:
            self.lines.signal[0] = -1
        else:
            self.lines.signal[0] = 0
