"""
GARCH(1,1) индикатор волатильности для FutOI дашборда.
Использует дневные свечи для оценки текущей и прогнозной волатильности.
"""

import numpy as np
import pandas as pd
from typing import Tuple


class GARCHIndicator:
    """
    GARCH(1,1) модель волатильности.
    sigma_t^2 = omega + alpha * r_{t-1}^2 + beta * sigma_{t-1}^2
    """
    
    def __init__(self, ticker: str):
        self.ticker = ticker
        self.omega = 0.000001
        self.alpha = 0.10
        self.beta = 0.85
        self.sigma2 = None
        self.fitted = False
        
    def fit(self, returns: np.ndarray) -> float:
        if len(returns) < 20:
            return np.std(returns) * np.sqrt(252) * 100
        
        var_long = np.var(returns)
        self.sigma2 = var_long
        
        for r in returns[-252:]:
            self.sigma2 = self.omega + self.alpha * (r ** 2) + self.beta * self.sigma2
        
        self.fitted = True
        return np.sqrt(self.sigma2) * np.sqrt(252) * 100
    
    def forecast(self, days: int = 1) -> float:
        if not self.fitted:
            return 0.0
        
        long_term_var = self.omega / (1 - self.alpha - self.beta)
        forecast_var = long_term_var + (self.sigma2 - long_term_var) * ((self.alpha + self.beta) ** days)
        
        return np.sqrt(max(forecast_var, 0)) * np.sqrt(252) * 100
    
    def get_volatility_regime(self, garch_vol: float, historical_vol: float) -> str:
        if garch_vol < 1.0:
            return "Низкая"
        elif garch_vol < 2.5:
            return "Нормальная"
        elif garch_vol < 5.0:
            return "Высокая"
        else:
            return "Экстремальная"
    
    def get_trend(self, garch_vol: float, prev_vol: float) -> str:
        if prev_vol is None:
            return "-"
        change = garch_vol - prev_vol
        if change > 0.5:
            return "📈 растёт"
        elif change < -0.5:
            return "📉 падает"
        else:
            return "▬ стабильна"


def calculate_garch_for_ticker(df_d1: pd.DataFrame, ticker: str) -> dict:
    if df_d1 is None or len(df_d1) < 20:
        return {'garch_vol': None, 'hist_vol': None, 'regime': 'Нет данных', 'trend': '-', 'forecast_5d': None}
    
    returns = df_d1['close'].pct_change().dropna().values
    
    garch = GARCHIndicator(ticker)
    garch_vol = garch.fit(returns)
    hist_vol = np.std(returns) * np.sqrt(252) * 100
    
    prev_returns = returns[-40:-20] if len(returns) >= 40 else returns[:-20]
    prev_vol = np.std(prev_returns) * np.sqrt(252) * 100 if len(prev_returns) > 0 else None
    
    regime = garch.get_volatility_regime(garch_vol, hist_vol)
    trend = garch.get_trend(garch_vol, prev_vol)
    forecast_5d = garch.forecast(5)
    
    return {'garch_vol': round(garch_vol, 2), 'hist_vol': round(hist_vol, 2), 'regime': regime, 'trend': trend, 'forecast_5d': round(forecast_5d, 2) if forecast_5d else None}
