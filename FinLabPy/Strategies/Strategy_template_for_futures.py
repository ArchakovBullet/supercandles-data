"""
Шаблон стратегии для фьючерсов MOEX
"""
import os
import backtrader as bt
import talib
import numpy as np
from MOEXPy.MOEXPy import MOEXPy

class FuturesStrategy(bt.Strategy):
    params = (
        ('ticker', 'GLDRUBF'),
        ('sma_fast', 10),
        ('sma_slow', 30),
        ('rsi_period', 14),
        ('rsi_oversold', 30),
        ('rsi_overbought', 70),
        ('stop_loss_atr', 2),  # 2 ATR для стоп-лосса
    )
    
    def __init__(self):
        # Индикаторы
        self.sma_fast = bt.indicators.SMA(self.data.close, period=self.params.sma_fast)
        self.sma_slow = bt.indicators.SMA(self.data.close, period=self.params.sma_slow)
        self.rsi = bt.indicators.RSI(self.data.close, period=self.params.rsi_period)
        self.atr = bt.indicators.ATR(self.data, period=14)
        
        # Для отслеживания позиций
        self.order = None
        self.stop_loss = None
        self.entry_price = None
        
    def next(self):
        if self.order:
            return
            
        if not self.position:
            # Сигнал на покупку
            if (self.sma_fast[0] > self.sma_slow[0] and 
                self.sma_fast[-1] <= self.sma_slow[-1] and
                self.rsi[0] < self.params.rsi_overbought):
                
                self.order = self.buy()
                self.entry_price = self.data.close[0]
                
            # Сигнал на продажу
            elif (self.sma_fast[0] < self.sma_slow[0] and 
                  self.sma_fast[-1] >= self.sma_slow[-1] and
                  self.rsi[0] > self.params.rsi_oversold):
                
                self.order = self.sell()
                self.entry_price = self.data.close[0]
        else:
            # Стоп-лосс
            stop_price = self.entry_price - (self.params.stop_loss_atr * self.atr[0]) if self.position.size > 0 \
                    else self.entry_price + (self.params.stop_loss_atr * self.atr[0])
            
            if (self.position.size > 0 and self.data.close[0] < stop_price) or \
               (self.position.size < 0 and self.data.close[0] > stop_price):
                self.order = self.close()
                
            # Выход по обратному сигналу
            elif (self.position.size > 0 and 
                  self.sma_fast[0] < self.sma_slow[0] and
                  self.sma_fast[-1] >= self.sma_slow[-1]):
                self.order = self.close()
                
            elif (self.position.size < 0 and 
                  self.sma_fast[0] > self.sma_slow[0] and
                  self.sma_fast[-1] <= self.sma_slow[-1]):
                self.order = self.close()