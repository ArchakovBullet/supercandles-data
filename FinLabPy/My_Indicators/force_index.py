"""
Force Index (Индекс Силы Элдера)

Формула:
    FI_raw = Volume × (Close_текущий - Close_предыдущий)
    FI_ema2 = EMA(FI_raw, period=2)   — краткосрочный
    FI_ema13 = EMA(FI_raw, period=13)  — среднесрочный

Интерпретация:
    • FI > 0 → покупатели контролируют рынок
    • FI < 0 → продавцы контролируют рынок
    • Новый максимум FI → продолжение роста
    • Новый минимум FI → продолжение падения
    • Бычья дивергенция: цена ↓, FI ↑ → BUY
    • Медвежья дивергенция: цена ↑, FI ↓ → SELL
"""

import backtrader as bt
import numpy as np


class ForceIndex(bt.Indicator):
    """
    Индекс Силы Элдера (Force Index)
    
    Линии:
        fi_ema2:  краткосрочный FI (EMA-2)
        fi_ema13: среднесрочный FI (EMA-13)
        fi_raw:   сырое значение FI (Volume × ΔPrice)
        
    Сигналы:
        signal: 1=BUY (бычья дивергенция или FI>0), -1=SELL
    """
    
    lines = ('fi_ema2', 'fi_ema13', 'signal', 'fi_raw')
    
    params = (
        ('ema_short', 2),    # Период короткой EMA
        ('ema_long', 13),    # Период длинной EMA
    )
    
    plotinfo = dict(
        plot=True,
        subplot=True,
        plotname='Force Index (Элдера)',
        plotlines=dict(
            fi_ema2=dict(color='blue', _name='FI(2)'),
            fi_ema13=dict(color='red', _name='FI(13)'),
            signal=dict(_method='bar', color='purple', alpha=0.3, _name='Сигнал'),
            fi_raw=dict(_plotskip=True),
        )
    )
    
    def __init__(self):
        # FI_raw = Volume × (Close - Previous Close)
        self.lines.fi_raw = self.data.volume * (self.data.close - self.data.close(-1))
        
        # Сглаживание через EMA
        self.lines.fi_ema2 = bt.indicators.EMA(self.lines.fi_raw, period=self.p.ema_short)
        self.lines.fi_ema13 = bt.indicators.EMA(self.lines.fi_raw, period=self.p.ema_long)
        
        # Максимумы/минимумы для дивергенций
        self.fi_max_5 = bt.indicators.Highest(self.lines.fi_ema13, period=5)
        self.fi_min_5 = bt.indicators.Lowest(self.lines.fi_ema13, period=5)
        self.price_max_5 = bt.indicators.Highest(self.data.close, period=5)
        self.price_min_5 = bt.indicators.Lowest(self.data.close, period=5)
        
    def next(self):
        fi = self.lines.fi_ema13[0]
        fi_prev = self.lines.fi_ema13[-1] if len(self) > 1 else 0
        fi_short = self.lines.fi_ema2[0]
        
        # По умолчанию нейтрально
        signal = 0
        
        # === СИГНАЛЫ Force Index ===
        
        # 1. Бычья дивергенция: цена ниже 5-дневного минимума, FI выше 5-дневного минимума
        if (self.data.close[0] <= self.price_min_5[0] * 1.01 and 
            fi > self.fi_min_5[0] and 
            fi_short > 0):
            signal = 1  # BUY
        
        # 2. Медвежья дивергенция: цена выше 5-дневного максимума, FI ниже 5-дневного максимума
        elif (self.data.close[0] >= self.price_max_5[0] * 0.99 and 
              fi < self.fi_max_5[0] and 
              fi_short < 0):
            signal = -1  # SELL
        
        # 3. FI(13) пересекает ноль вверх → бычий импульс
        elif fi > 0 and fi_prev <= 0:
            signal = 1  # BUY
        
        # 4. FI(13) пересекает ноль вниз → медвежий импульс
        elif fi < 0 and fi_prev >= 0:
            signal = -1  # SELL
        
        self.lines.signal[0] = signal
