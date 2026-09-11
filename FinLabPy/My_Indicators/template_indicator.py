"""
Шаблон для создания пользовательских индикаторов
"""
import backtrader as bt
import talib
import numpy as np


class TemplateIndicator(bt.Indicator):
    """
    Шаблон индикатора
    
    Параметры:
        period: период индикатора (по умолчанию 14)
    """
    
    lines = ('indicator_line', 'signal_line')  # Объявляем линии индикатора
    params = (
        ('period', 14),
        ('smooth', 3),
    )
    
    plotinfo = dict(
        plot=True,
        subplot=True,
        plotname='Template Indicator'
    )
    
    def __init__(self):
        # Доступ к данным
        close = self.data.close.array
        
        # Расчет через TA-Lib (если нужно)
        # self.rsi = talib.RSI(close, timeperiod=self.p.period)
        
        # Или через встроенные индикаторы BackTrader
        self.sma = bt.indicators.SMA(self.data, period=self.p.period)
        
    def next(self):
        # Вычисление значений на каждом баре
        self.lines.indicator_line[0] = self.sma[0]
        self.lines.signal_line[0] = self.sma[0] * 1.05


class MyRSI(bt.Indicator):
    """
    RSI с дополнительной сигнальной линией
    """
    lines = ('rsi', 'signal')
    params = (
        ('period', 14),
        ('signal_period', 9),
        ('overbought', 70),
        ('oversold', 30),
    )
    
    plotinfo = dict(
        plot=True,
        subplot=True,
        plotname='My RSI',
        plotlines=dict(
            rsi=dict(color='blue', _name='RSI'),
            signal=dict(color='red', _name='Signal')
        )
    )
    
    def __init__(self):
        # Расчет RSI через TA-Lib
        self.lines.rsi = bt.indicators.RSI(self.data, period=self.p.period)
        # Сигнальная линия - SMA от RSI
        self.lines.signal = bt.indicators.SMA(self.lines.rsi, period=self.p.signal_period)
        
    def next(self):
        pass
