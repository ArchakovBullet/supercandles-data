"""
Индекс Армса (Arms Index / TRIN) — ширина рынка акций.
Измеряет соотношение растущих/падающих акций к их объёмам.

TRIN = (Кол-во выросших / Кол-во упавших) / (Объём выросших / Объём упавших)

> 1.0 — медвежий сигнал (объём в падающих)
< 1.0 — бычий сигнал (объём в растущих)
> 1.5 — экстремальная перепроданность (возможен отскок)
< 0.5 — экстремальная перекупленность (возможна коррекция)
"""

import pandas as pd
import numpy as np
from pathlib import Path


def calculate_trin(data_dir=None, tickers=None):
    """
    Рассчитывает индекс Армса (TRIN) на основе D1-свечей.
    
    Параметры:
    - data_dir: путь к папке с D1-свечами
    - tickers: список тикеров (по умолчанию — 10 основных акций)
    
    Возвращает:
    - trin: значение индекса Армса
    - advancing: кол-во выросших акций
    - declining: кол-во упавших акций
    - adv_volume: объём в выросших
    - dec_volume: объём в упавших
    - signal: BULLISH / BEARISH / NEUTRAL
    - level: норма / перекупленность / перепроданность
    """
    if data_dir is None:
        data_dir = Path('/root/finlab/data/candles')
    
    if tickers is None:
        tickers = ['SBER', 'GAZP', 'GMKN', 'LKOH', 'HYDR', 'IRAO', 'PLZL', 'ROSN', 'TATN', 'VTBR', 'AFKS', 'T']
    
    advancing = 0
    declining = 0
    adv_volume = 0
    dec_volume = 0
    
    for ticker in tickers:
        f = Path(data_dir) / f"{ticker}_D1.parquet"
        if not f.exists():
            continue
        
        try:
            df = pd.read_parquet(f)
            if len(df) < 2:
                continue
            
            last = df.iloc[-1]
            prev = df.iloc[-2]
            
            change = last['close'] - prev['close']
            volume = last['volume'] if 'volume' in df.columns else 0
            
            if change > 0:
                advancing += 1
                adv_volume += volume
            elif change < 0:
                declining += 1
                dec_volume += volume
        except:
            continue
    
    if declining == 0 or dec_volume == 0:
        return {
            'trin': 0,
            'advancing': advancing,
            'declining': declining,
            'adv_volume': int(adv_volume),
            'dec_volume': int(dec_volume),
            'signal': 'NEUTRAL',
            'level': 'Нет данных',
            'note': 'Недостаточно данных для расчёта'
        }
    
    # TRIN
    adv_dec_ratio = advancing / declining
    vol_ratio = adv_volume / dec_volume if dec_volume > 0 else 1
    trin = adv_dec_ratio / vol_ratio if vol_ratio > 0 else 1
    
    trin = round(trin, 2)
    
    # Сигнал
    if trin < 0.5:
        signal = 'BULLISH'
        level = '🔴 Экстремальная перекупленность'
        note = 'Рынок перегрет. Возможна коррекция вниз.'
    elif trin < 0.8:
        signal = 'BULLISH'
        level = '🟢 Перекупленность'
        note = 'Объём сконцентрирован в растущих акциях. Бычий сигнал.'
    elif trin < 1.0:
        signal = 'BULLISH'
        level = '🟢 Умеренно бычий'
        note = 'Покупатели контролируют рынок.'
    elif trin < 1.2:
        signal = 'BEARISH'
        level = '🟡 Умеренно медвежий'
        note = 'Продавцы начинают давить.'
    elif trin < 1.5:
        signal = 'BEARISH'
        level = '🟠 Медвежий'
        note = 'Объём сконцентрирован в падающих акциях.'
    else:
        signal = 'BEARISH'
        level = '🔴 Экстремальная перепроданность'
        note = 'Паника на рынке. Возможен отскок вверх.'
    
    return {
        'trin': trin,
        'advancing': advancing,
        'declining': declining,
        'adv_volume': int(adv_volume),
        'dec_volume': int(dec_volume),
        'signal': signal,
        'level': level,
        'note': note
    }
