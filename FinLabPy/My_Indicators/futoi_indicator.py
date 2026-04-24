"""
Индикатор FutOI - анализ открытых позиций физических и юридических лиц
Поддерживает внутридневные обновления (каждые 5 минут)

Версия 2.1 - исправлено: данные FutOI на все бары (forward-fill)
"""

import backtrader as bt
import os
from datetime import datetime, timedelta
from collections import defaultdict
from MOEXPy.MOEXPy import MOEXPy


class FutOIIndicator(bt.Indicator):
    """
    Индикатор открытых позиций (FutOI) с разделением на физ/юр лиц
    
    Линии:
        phys_net: нетто-позиция физиков (млн)
        jur_net: нетто-позиция юрлиц (млн)
        phys_change: изменение позиции физиков за период (млн)
        phys_long: длинные позиции физиков (млн)
        phys_short: короткие позиции физиков (млн)
        
    Параметры:
        ticker: тикер фьючерса (по умолчанию 'GLDRUBF')
        lookback: дней истории
        update_intraday: обновлять внутри дня (True для M1/M10)
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
        self._futoi_data = {}       # Дневные агрегированные данные
        self._intraday_data = {}    # Внутридневные данные
        
        # Загружаем данные
        self._load_futoi_data()
    
    def _init_api(self):
        """Инициализация API MOEX"""
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
        """Загрузка данных FutOI с MOEX"""
        if not self._init_api():
            return
        
        try:
            dt_till = datetime.now()
            dt_from = dt_till - timedelta(days=self.p.lookback + 3)
            
            data = self.api.get_futoi(self.p.ticker, dt_from, dt_till)
            
            if 'futoi' in data and 'data' in data['futoi']:
                cols = data['futoi']['columns']
                rows = data['futoi']['data']
                idx = {c: i for i, c in enumerate(cols)}
                
                # Собираем внутридневные данные
                for row in rows:
                    date = str(row[idx['tradedate']])[:10]
                    time = str(row[idx['tradetime']])
                    clgroup = row[idx['clgroup']]
                    pos_long = int(row[idx['pos_long']]) if row[idx['pos_long']] else 0
                    pos_short = abs(int(row[idx['pos_short']])) if row[idx['pos_short']] else 0
                    
                    key = f"{date}T{time}"
                    
                    if key not in self._intraday_data:
                        self._intraday_data[key] = {'FIZ_long': 0, 'FIZ_short': 0, 'YUR_long': 0, 'YUR_short': 0}
                    
                    self._intraday_data[key][f'{clgroup}_long'] += pos_long
                    self._intraday_data[key][f'{clgroup}_short'] += pos_short
                
                # Группируем по дням (берем ПОСЛЕДНЕЕ значение за день)
                day_last = {}
                for key in sorted(self._intraday_data.keys()):
                    date = key[:10]
                    day_last[date] = self._intraday_data[key]
                
                for date, d in day_last.items():
                    self._futoi_data[date] = {
                        'phys_net': (d['FIZ_long'] - d['FIZ_short']) / 1_000_000,
                        'jur_net': (d['YUR_long'] - d['YUR_short']) / 1_000_000,
                        'phys_long': d['FIZ_long'] / 1_000_000,
                        'phys_short': d['FIZ_short'] / 1_000_000,
                    }
                
        except Exception as e:
            print(f"⚠️ FutOI: ошибка загрузки - {e}")
    
    def _get_intraday_value(self, bar_datetime):
        """Получить ближайшее внутридневное значение"""
        bar_str = bar_datetime.strftime('%Y-%m-%dT%H:%M:00')
        
        if bar_str in self._intraday_data:
            d = self._intraday_data[bar_str]
            return {
                'phys_net': (d['FIZ_long'] - d['FIZ_short']) / 1_000_000,
                'jur_net': (d['YUR_long'] - d['YUR_short']) / 1_000_000,
                'phys_long': d['FIZ_long'] / 1_000_000,
                'phys_short': d['FIZ_short'] / 1_000_000,
            }
        
        sorted_keys = sorted(self._intraday_data.keys())
        for key in reversed(sorted_keys):
            if key <= bar_str:
                d = self._intraday_data[key]
                return {
                    'phys_net': (d['FIZ_long'] - d['FIZ_short']) / 1_000_000,
                    'jur_net': (d['YUR_long'] - d['YUR_short']) / 1_000_000,
                    'phys_long': d['FIZ_long'] / 1_000_000,
                    'phys_short': d['FIZ_short'] / 1_000_000,
                }
        
        if sorted_keys:
            d = self._intraday_data[sorted_keys[0]]
            return {
                'phys_net': (d['FIZ_long'] - d['FIZ_short']) / 1_000_000,
                'jur_net': (d['YUR_long'] - d['YUR_short']) / 1_000_000,
                'phys_long': d['FIZ_long'] / 1_000_000,
                'phys_short': d['FIZ_short'] / 1_000_000,
            }
        
        return None
    
    def _get_daily_value(self, bar_date):
        """Получить дневное значение (forward-fill если нет данных)"""
        date_str = bar_date.strftime('%Y-%m-%d')
        
        # Точное совпадение
        if date_str in self._futoi_data:
            return self._futoi_data[date_str]
        
        # Ближайшая предыдущая дата
        sorted_dates = sorted(self._futoi_data.keys())
        for d in reversed(sorted_dates):
            if d <= date_str:
                return self._futoi_data[d]
        
        # Нет предыдущих — берем первую доступную (будущие данные для старых баров)
        if sorted_dates:
            return self._futoi_data[sorted_dates[0]]
        
        return None
    
    def next(self):
        """Вызывается на каждом баре"""
        bar_dt = self.data.datetime.datetime()
        
        if self.p.update_intraday:
            futoi = self._get_intraday_value(bar_dt)
        else:
            futoi = self._get_daily_value(bar_dt)
        
        # Если данных нет совсем — заполняем нулями
        if futoi is None:
            futoi = {'phys_net': 0, 'jur_net': 0, 'phys_long': 0, 'phys_short': 0}
        
        # Изменение позиции физиков
        prev_net = self.lines.phys_net[-1] if len(self.lines.phys_net) > 1 else 0
        
        self.lines.phys_net[0] = futoi['phys_net']
        self.lines.jur_net[0] = futoi['jur_net']
        self.lines.phys_long[0] = futoi['phys_long']
        self.lines.phys_short[0] = futoi['phys_short']
        self.lines.phys_change[0] = futoi['phys_net'] - prev_net if prev_net != 0 else 0


class FutOISignal(bt.Indicator):
    """Торговый сигнал на основе FutOI"""
    
    lines = ('signal',)
    
    params = (
        ('threshold', 5),
    )
    
    plotinfo = dict(
        plot=True,
        subplot=True,
        plotname='FutOI Signal',
        plotlines=dict(
            signal=dict(_method='bar', color='blue', alpha=0.5),
        )
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
