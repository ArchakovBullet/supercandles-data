"""
Классификатор типов алгоритмов на рынке (Algopack-подход).
Определяет доминирующие типы роботов: HFT, VWAP/TWAP, Iceberg, Институциональные.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple


class RobotClassifier:
    """
    Классификатор алгоритмической активности на рынке.
    
    Типы:
    - HFT: высокая частота мелких сделок + высокая концентрация
    - VWAP/TWAP: равномерное давление в течение дня
    - Iceberg: экстремальная концентрация + узкий диапазон цены
    - Институциональные: рост позиций юриков + падение позиций физиков
    """
    
    def __init__(self, ticker: str):
        self.ticker = ticker
        
    def classify(self,
                 hi2_value: float,
                 trades_count: int,
                 avg_trade_size: float,
                 price_range_pct: float,
                 phys_net: float,
                 jur_net: float,
                 supercandles_disb: List[float] = None) -> Dict:
        """
        Классифицирует текущий режим рынка.
        
        Returns:
            dict с типами роботов и их активностью (0-100)
        """
        result = {
            'hft': {'active': False, 'score': 0, 'desc': ''},
            'vwap': {'active': False, 'score': 0, 'desc': ''},
            'iceberg': {'active': False, 'score': 0, 'desc': ''},
            'institutional': {'active': False, 'score': 0, 'desc': ''},
            'dominant': None
        }
        
        # 1. HFT: высокая частота + маленький размер сделки + высокая концентрация
        hft_score = 0
        if trades_count > 1000:
            hft_score += 30
        if avg_trade_size < 5 and avg_trade_size > 0:
            hft_score += 25
        if hi2_value > 500:
            hft_score += 25
        if price_range_pct < 0.5:
            hft_score += 20
        
        if hft_score >= 50:
            result['hft'] = {
                'active': True,
                'score': hft_score,
                'desc': f'Высокочастотные роботы активны ({hft_score}/100). Рынок быстрый, низкая предсказуемость.'
            }
        
        # 2. VWAP/TWAP: равномерный дисбаланс по часам
        vwap_score = 0
        if supercandles_disb:
            disb_std = np.std(supercandles_disb)
            if disb_std < 0.15:
                vwap_score += 40
            if len(supercandles_disb) >= 6:
                vwap_score += 30
            if abs(np.mean(supercandles_disb)) < 0.1:
                vwap_score += 30
        
        if vwap_score >= 50:
            direction = 'покупку' if np.mean(supercandles_disb) > 0 else 'продажу'
            result['vwap'] = {
                'active': True,
                'score': vwap_score,
                'desc': f'VWAP/TWAP алгоритмы работают на {direction} ({vwap_score}/100). Крупный игрок на рынке.'
            }
        
        # 3. Iceberg: экстремальная концентрация + узкий диапазон
        iceberg_score = 0
        if hi2_value > 600:
            iceberg_score += 40
        if price_range_pct < 1.0:
            iceberg_score += 30
        if phys_net > 50 or jur_net > 40:
            iceberg_score += 30
        
        if iceberg_score >= 50:
            result['iceberg'] = {
                'active': True,
                'score': iceberg_score,
                'desc': f'Iceberg-заявки обнаружены ({iceberg_score}/100). Крупный игрок скрывает позицию.'
            }
        
        # 4. Институциональные: юрики набирают/сбрасывают позицию
        inst_score = 0
        if abs(jur_net) > 30:
            inst_score += 40
        if phys_net > 50:
            inst_score += 30
        if hi2_value > 300:
            inst_score += 30
        
        if inst_score >= 50:
            action = 'продают' if jur_net > 20 else ('покупают' if jur_net < -20 else 'накапливают позицию')
            result['institutional'] = {
                'active': True,
                'score': inst_score,
                'desc': f'Институциональные игроки {action} ({inst_score}/100). Давление продолжится.'
            }
        
        # Определяем доминирующий тип
        scores = {
            'HFT-скальперы': result['hft']['score'],
            'VWAP/TWAP': result['vwap']['score'],
            'Iceberg': result['iceberg']['score'],
            'Институциональные': result['institutional']['score']
        }
        max_type = max(scores, key=scores.get)
        if scores[max_type] >= 50:
            result['dominant'] = max_type
        
        return result


def classify_market(ticker: str,
                    hi2_value: float,
                    tradestats_df: pd.DataFrame,
                    df_d1: pd.DataFrame,
                    phys_net: float,
                    jur_net: float,
                    supercandles_df: pd.DataFrame = None) -> Dict:
    """
    Быстрая классификация рынка для дашборда.
    """
    classifier = RobotClassifier(ticker)
    
    # Параметры из TradeStats
    if tradestats_df is not None and not tradestats_df.empty:
        trades_count = len(tradestats_df)
        avg_trade_size = tradestats_df['vol'].mean() / tradestats_df['trades'].mean() if 'trades' in tradestats_df.columns else 10
    else:
        trades_count = 0
        avg_trade_size = 10
    
    # Диапазон цены
    if df_d1 is not None and len(df_d1) >= 20:
        price_range_pct = ((df_d1['high'].iloc[-20:].max() - df_d1['low'].iloc[-20:].min()) / df_d1['close'].iloc[-1]) * 100
    else:
        price_range_pct = 2.0
    
    # Super Candles дисбаланс
    disb_list = []
    if supercandles_df is not None and not supercandles_df.empty:
        if 'disb' in supercandles_df.columns:
            disb_list = supercandles_df['disb'].tail(8).tolist()
    
    result = classifier.classify(
        hi2_value=hi2_value if hi2_value else 0,
        trades_count=trades_count,
        avg_trade_size=avg_trade_size,
        price_range_pct=price_range_pct,
        phys_net=phys_net,
        jur_net=jur_net,
        supercandles_disb=disb_list
    )
    
    return result


if __name__ == '__main__':
    # Тест
    c = RobotClassifier('TEST')
    r = c.classify(
        hi2_value=450,
        trades_count=2000,
        avg_trade_size=3.5,
        price_range_pct=0.8,
        phys_net=60,
        jur_net=35,
        supercandles_disb=[0.02, -0.01, 0.03, -0.02, 0.01, 0.0]
    )
    for k, v in r.items():
        if k != 'dominant':
            print(f"{k}: {v['active']} ({v['score']})")
    print(f"Dominant: {r['dominant']}")
