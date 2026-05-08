"""
HMM стратегия: вход только в UP-режиме, выход при смене режима.
Сравнение с Buy & Hold.
"""
import os, sys
from pathlib import Path
project_root = Path(__file__).parent.parent.parent if '__file__' in dir() else Path('.').absolute()
sys.path.insert(0, str(project_root))

import numpy as np
import polars as pl
from hmmlearn import hmm
from sklearn.preprocessing import StandardScaler
from FinLabPy.DataCollectors.osengine_loader import OsEngineLoader
from FinLabPy.My_Indicators.technical_features import add_technical_features

FEATURES = ['returns', 'volatility', 'volume_ratio', 'trend_strength',
            'price_vs_sma20', 'price_vs_sma50', 'rsi', 'macd_hist', 'bb_position']


def run_hmm_strategy(df, n_regimes=4):
    """HMM стратегия: BUY при UP-режиме, SELL при смене."""
    # Очистка и подготовка
    df_clean = df[FEATURES + ['date', 'close']].drop_nulls()
    for col in FEATURES:
        df_clean = df_clean.filter(pl.col(col).is_finite())
    
    X = df_clean[FEATURES].to_numpy()
    closes = df_clean['close'].to_numpy()
    dates = df_clean['date'].to_list()
    
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    model = hmm.GaussianHMM(n_components=n_regimes, covariance_type='full', n_iter=1000, random_state=42)
    model.fit(X_scaled)
    regimes = model.predict(X_scaled)
    
    # Определяем доходность каждого режима
    returns = np.diff(closes) / closes[:-1]
    regime_returns = {}
    for r in range(n_regimes):
        mask = regimes[:-1] == r
        if mask.sum() > 0:
            regime_returns[r] = returns[mask].mean()
    
    # Находим UP-режимы (доходность > 0.05%/день)
    up_regimes = [r for r, ret in regime_returns.items() if ret > 0.0005]
    
    if not up_regimes:
        return None, None, None, None
    
    # Симуляция торговли
    in_position = False
    buy_price = 0
    trades = []
    daily_returns = []
    
    for i in range(1, len(regimes)):
        current_regime = regimes[i]
        
        if not in_position and current_regime in up_regimes:
            # Вход
            in_position = True
            buy_price = closes[i]
            trades.append({'date': dates[i], 'action': 'BUY', 'price': buy_price})
        elif in_position and current_regime not in up_regimes:
            # Выход
            in_position = False
            sell_price = closes[i]
            pnl_pct = (sell_price / buy_price - 1) * 100
            trades.append({'date': dates[i], 'action': 'SELL', 'price': sell_price, 'pnl_pct': pnl_pct})
        
        # Дневная доходность стратегии
        if in_position and i > 0:
            daily_returns.append((closes[i] / closes[i-1] - 1) * 100)
        else:
            daily_returns.append(0)
    
    # Buy & Hold
    bh_return = (closes[-1] / closes[0] - 1) * 100
    
    # Метрики стратегии
    strategy_returns = np.array(daily_returns)
    total_return = (np.prod(1 + strategy_returns / 100) - 1) * 100 if len(strategy_returns) > 0 else 0
    
    win_trades = [t for t in trades if t['action'] == 'SELL' and t['pnl_pct'] > 0]
    all_trades = [t for t in trades if t['action'] == 'SELL']
    win_rate = 100 * len(win_trades) / len(all_trades) if all_trades else 0
    
    return {
        'trades': len(all_trades),
        'win_rate': win_rate,
        'total_pnl': sum(t['pnl_pct'] for t in all_trades),
        'strategy_return': total_return,
        'bh_return': bh_return,
        'up_regimes': len(up_regimes),
        'switches': (regimes[1:] != regimes[:-1]).sum(),
    }, trades, regimes, closes


if __name__ == '__main__':
    loader = OsEngineLoader()
    
    print('HMM СТРАТЕГИЯ: ТОРГОВЛЯ В UP-РЕЖИМЕ\n')
    print(f'{"Инструмент":20s} | {"Сделок":6s} | {"Win":5s} | {"Страт.PnL":>9s} | {"B&H PnL":>9s} | {"Дельта":>8s}')
    print(f'{"-"*75}')
    
    all_results = []
    
    for instrument in loader.list_instruments():
        df_raw = loader.load(instrument)
        df_daily = loader.to_daily(df_raw)
        
        if len(df_daily) < 100:
            continue
        
        df_features = add_technical_features(df_daily)
        result, trades, regimes, closes = run_hmm_strategy(df_features, n_regimes=4)
        
        if result is None:
            continue
        
        delta = result['strategy_return'] - result['bh_return']
        
        print(f'{instrument:20s} | {result["trades"]:4d}  | {result["win_rate"]:3.0f}% | {result["strategy_return"]:+8.1f}% | {result["bh_return"]:+8.1f}% | {delta:+7.1f}%')
        
        all_results.append({'instrument': instrument, **result, 'delta': delta})
    
    # Итоги
    print(f'\n{"="*60}')
    print('ТОП ПО ПРИРОСТУ НАД B&H:')
    all_results.sort(key=lambda x: x['delta'], reverse=True)
    for r in all_results[:5]:
        print(f'  {r["instrument"]:20s}: +{r["delta"]:.1f}% (страт: {r["strategy_return"]:.1f}%, B&H: {r["bh_return"]:.1f}%)')
