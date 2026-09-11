"""
Индикатор агрессивности рынка на основе TradeStats данных.
Оценивает соотношение рыночных и лимитных ордеров, силу импульса.
"""

import pandas as pd
import numpy as np
from typing import Tuple


class MarketAggression:
    """
    Анализатор агрессивности рынка.
    Высокий коэффициент = паника/импульс (рыночные ордера преобладают).
    Низкий коэффициент = спокойный рынок (лимитные ордера преобладают).
    """
    
    def __init__(self, ticker: str):
        self.ticker = ticker
        
    def calculate_aggression_score(self, 
                                    buy_volume: float, 
                                    sell_volume: float,
                                    total_volume: float,
                                    price_change_pct: float,
                                    hi2: float = None) -> dict:
        """
        Рассчитывает коэффициент агрессивности (0-100).
        
        Args:
            buy_volume: объём покупок
            sell_volume: объём продаж
            total_volume: общий объём
            price_change_pct: изменение цены в %
            hi2: концентрация (опционально)
            
        Returns:
            dict с ключами: score, level, direction, interpretation
        """
        if total_volume == 0:
            return {'score': 50, 'level': 'Нет данных', 'direction': '—', 'interpretation': 'Нет данных'}
        
        # 1. Дисбаланс объёмов (0-40 баллов)
        imbalance = abs(buy_volume - sell_volume) / total_volume
        imbalance_score = min(imbalance * 40, 40)
        
        # 2. Направление агрессии (0-30 баллов)
        if buy_volume > sell_volume:
            direction = 'Покупатели'
            direction_mult = 1
        else:
            direction = 'Продавцы'
            direction_mult = -1
        
        # Сила направления
        direction_ratio = max(buy_volume, sell_volume) / min(buy_volume, sell_volume) if min(buy_volume, sell_volume) > 0 else 1
        direction_score = min(direction_ratio * 10, 30)
        
        # 3. Импульс цены (0-20 баллов)
        impulse_score = min(abs(price_change_pct) * 10, 20)
        
        # 4. Концентрация (0-10 баллов) — высокая концентрация усиливает агрессию
        concentration_score = 0
        if hi2 is not None:
            if hi2 > 500:
                concentration_score = 10
            elif hi2 > 300:
                concentration_score = 5
        
        # Итоговый скор
        total_score = imbalance_score + direction_score + impulse_score + concentration_score
        total_score = min(total_score, 100)
        
        # Уровень
        if total_score >= 70:
            level = '🔴 Высокая'
        elif total_score >= 40:
            level = '🟡 Средняя'
        else:
            level = '🟢 Низкая'
        
        # Интерпретация
        if total_score >= 70:
            interpretation = f'{direction} агрессивно входят в рынок. Паника или сильный импульс.'
        elif total_score >= 40:
            interpretation = f'{direction} умеренно активны. Нормальный рыночный поток.'
        else:
            interpretation = 'Рынок спокоен. Преобладают лимитные заявки.'
        
        return {
            'score': round(total_score, 1),
            'level': level,
            'direction': direction,
            'direction_mult': direction_mult,
            'interpretation': interpretation,
            'imbalance_pct': round(imbalance * 100, 1),
            'volume_ratio': round(direction_ratio, 1)
        }
    
    def analyze_tradestats(self, tradestats_df: pd.DataFrame, price_change_pct: float, hi2: float = None) -> dict:
        """
        Анализирует агрессивность из TradeStats данных.
        
        Args:
            tradestats_df: DataFrame с колонками buy_volume, sell_volume или аналогичными
            price_change_pct: изменение цены
            hi2: концентрация
            
        Returns:
            dict с результатами
        """
        if tradestats_df is None or tradestats_df.empty:
            return {'score': 50, 'level': 'Нет данных', 'direction': '—', 'interpretation': 'Нет данных'}
        
        # Суммируем объёмы
        buy_vol = tradestats_df.get('vol_b', pd.Series([0])).sum()
        sell_vol = tradestats_df.get('vol_s', pd.Series([0])).sum()
        total_vol = buy_vol + sell_vol
        
        return self.calculate_aggression_score(buy_vol, sell_vol, total_vol, price_change_pct, hi2)


def calculate_aggression_for_ticker(tradestats_df: pd.DataFrame, 
                                     df_d1: pd.DataFrame,
                                     hi2_value: float = None,
                                     ticker: str = 'UNKNOWN') -> dict:
    """
    Быстрый расчёт агрессивности для тикера.
    """
    if df_d1 is None or len(df_d1) < 2:
        price_change_pct = 0
    else:
        last_close = df_d1['close'].iloc[-1]
        prev_close = df_d1['close'].iloc[-2]
        price_change_pct = ((last_close - prev_close) / prev_close) * 100 if prev_close > 0 else 0
    
    analyzer = MarketAggression(ticker)
    return analyzer.analyze_tradestats(tradestats_df, price_change_pct, hi2_value)


if __name__ == '__main__':
    # Тест
    analyzer = MarketAggression('TEST')
    result = analyzer.calculate_aggression_score(
        buy_volume=1500, sell_volume=1000, total_volume=2500,
        price_change_pct=1.5, hi2=450
    )
    print(result)
