"""
Кросс-рыночный контекст для FutOI дашборда.
Анализирует связанные инструменты для подтверждения сигналов.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, Optional


# Пары для кросс-рыночного анализа
CROSS_PAIRS = {
    'CNYRUBF': {'pair': 'USDRUBF', 'type': 'forex', 'desc': 'Юань vs Доллар'},
    'GAZPF':   {'pair': 'GAZP',    'type': 'stock', 'desc': 'Фьючерс vs Акция Газпром'},
    'GLDRUBF': {'pair': 'IMOEXF',  'type': 'index', 'desc': 'Золото vs Индекс МосБиржи'},
    'IMOEXF':  {'pair': 'SBERF',   'type': 'stock', 'desc': 'Индекс vs Сбер'},
    'SBERF':   {'pair': 'SBER',    'type': 'stock', 'desc': 'Фьючерс vs Акция Сбер'},
}


class CrossMarketAnalyzer:
    """Анализатор кросс-рыночных связей."""
    
    def __init__(self, ticker: str, data_root: str = '/root/finlab/data'):
        self.ticker = ticker
        self.data_root = Path(data_root)
        self.pair_info = CROSS_PAIRS.get(ticker)
        
    def get_pair_data(self) -> Optional[pd.DataFrame]:
        """Загружает данные связанного инструмента."""
        if not self.pair_info:
            return None
        pair = self.pair_info['pair']
        path = self.data_root / 'candles' / f'{pair}_D1.parquet'
        if path.exists():
            return pd.read_parquet(path)
        return None
    
    def calculate_correlation(self, df1: pd.DataFrame, df2: pd.DataFrame, days: int = 20) -> float:
        """Корреляция доходностей за N дней."""
        if df1 is None or df2 is None or len(df1) < days or len(df2) < days:
            return 0
        
        common_dates = set(df1['begin'].dt.date) & set(df2['begin'].dt.date)
        if len(common_dates) < days:
            return 0
        
        ret1 = df1[df1['begin'].dt.date.isin(common_dates)].set_index('begin')['close'].pct_change().dropna()
        ret2 = df2[df2['begin'].dt.date.isin(common_dates)].set_index('begin')['close'].pct_change().dropna()
        
        common = ret1.index.intersection(ret2.index)
        if len(common) < days:
            return 0
        
        return ret1[common].tail(days).corr(ret2[common].tail(days))
    
    def calculate_spread(self, df1: pd.DataFrame, df2: pd.DataFrame, days: int = 20) -> Dict:
        """Анализ спреда между двумя инструментами."""
        if df1 is None or df2 is None:
            return {'zscore': 0, 'direction': '—', 'width_pct': 0}
        
        common_dates = set(df1['begin'].dt.date) & set(df2['begin'].dt.date)
        if len(common_dates) < days:
            return {'zscore': 0, 'direction': '—', 'width_pct': 0}
        
        p1 = df1[df1['begin'].dt.date.isin(common_dates)].set_index('begin')['close']
        p2 = df2[df2['begin'].dt.date.isin(common_dates)].set_index('begin')['close']
        
        common = p1.index.intersection(p2.index)
        p1 = p1[common].tail(days)
        p2 = p2[common].tail(days)
        
        # Нормализованные цены (100 = последняя цена)
        norm1 = p1 / p1.iloc[-1] * 100
        norm2 = p2 / p2.iloc[-1] * 100
        spread = norm1 - norm2
        
        zscore = (spread.iloc[-1] - spread.mean()) / spread.std() if spread.std() > 0 else 0
        width_pct = abs(spread.iloc[-1])
        
        if zscore > 1.5:
            direction = f'{self.ticker} переоценён относительно {self.pair_info["pair"]}'
        elif zscore < -1.5:
            direction = f'{self.ticker} недооценён относительно {self.pair_info["pair"]}'
        else:
            direction = 'Спред в норме'
        
        return {'zscore': round(zscore, 2), 'direction': direction, 'width_pct': round(width_pct, 1)}
    
    def analyze(self, df_main: pd.DataFrame) -> Dict:
        """Полный кросс-рыночный анализ."""
        if not self.pair_info:
            return {'available': False, 'reason': 'Нет пары для анализа'}
        
        df_pair = self.get_pair_data()
        if df_pair is None:
            return {'available': False, 'reason': f'Нет данных по {self.pair_info["pair"]}'}
        
        corr = self.calculate_correlation(df_main, df_pair)
        spread = self.calculate_spread(df_main, df_pair)
        
        # Интерпретация
        signal = 'нейтральный'
        if corr > 0.7 and abs(spread['zscore']) > 1.5:
            signal = 'подтверждает' if spread['zscore'] < 0 else 'противоречит'
        elif corr < -0.7:
            signal = 'обратная связь'
        
        return {
            'available': True,
            'pair': self.pair_info['pair'],
            'pair_desc': self.pair_info['desc'],
            'correlation': round(corr, 2),
            'spread_zscore': spread['zscore'],
            'spread_direction': spread['direction'],
            'spread_width': spread['width_pct'],
            'signal': signal,
        }


def analyze_cross_market(ticker: str, df_main: pd.DataFrame, data_root: str = '/root/finlab/data') -> Dict:
    """Быстрый кросс-рыночный анализ для дашборда."""
    analyzer = CrossMarketAnalyzer(ticker, data_root)
    return analyzer.analyze(df_main)


if __name__ == '__main__':
    data_root = '/root/finlab/data'
    df = pd.read_parquet(f'{data_root}/candles/CNYRUBF_D1.parquet')
    result = analyze_cross_market('CNYRUBF', df, data_root)
    print(result)
