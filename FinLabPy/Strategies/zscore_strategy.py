"""
Z-Score стратегия: вход при отклонении на 2σ от SMA, выход при возврате к средней.
Тест на данных OsEngine (Аэрофлот).
"""
import os, sys
from pathlib import Path
project_root = Path(__file__).parent.parent.parent if '__file__' in dir() else Path('.').absolute()
sys.path.insert(0, str(project_root))

import numpy as np
import polars as pl
from FinLabPy.DataCollectors.osengine_loader import OsEngineLoader

def zscore_strategy(df, entry_z=2.0, exit_z=0.0, sma_period=20):
    """
    Z-Score стратегия.
    - entry_z: вход при |z| > entry_z (2σ по умолчанию)
    - exit_z: выход при |z| < exit_z (возврат к средней)
    """
    close = df['close'].to_numpy()
    
    # SMA и стандартное отклонение
    sma = np.full(len(close), np.nan)
    std = np.full(len(close), np.nan)
    
    for i in range(sma_period - 1, len(close)):
        sma[i] = close[i-sma_period+1:i+1].mean()
        std[i] = close[i-sma_period+1:i+1].std()
    
    z_score = (close - sma) / std
    
    # Сигналы
    position = 0  # 0=нет, 1=long, -1=short
    trades = []
    
    for i in range(sma_period, len(close)):
        z = z_score[i]
        
        if position == 0:
            if z < -entry_z:
                position = 1
                trades.append({'date': df['date'][i], 'action': 'BUY', 'price': close[i], 'z': z})
            elif z > entry_z:
                position = -1
                trades.append({'date': df['date'][i], 'action': 'SELL', 'price': close[i], 'z': z})
        elif position == 1:
            if z > exit_z:
                trades.append({'date': df['date'][i], 'action': 'CLOSE_LONG', 'price': close[i], 'z': z})
                position = 0
        elif position == -1:
            if z < exit_z:
                trades.append({'date': df['date'][i], 'action': 'CLOSE_SHORT', 'price': close[i], 'z': z})
                position = 0
    
    return trades, z_score


def analyze_trades(trades):
    """Анализ сделок."""
    if not trades:
        return
    
    long_trades = []
    short_trades = []
    current_buy = None
    current_sell = None
    
    for t in trades:
        if t['action'] == 'BUY':
            current_buy = t
        elif t['action'] == 'CLOSE_LONG' and current_buy:
            pnl_pct = (t['price'] / current_buy['price'] - 1) * 100
            long_trades.append({**current_buy, 'exit_date': t['date'], 'exit_price': t['price'], 'pnl_pct': pnl_pct})
            current_buy = None
        elif t['action'] == 'SELL':
            current_sell = t
        elif t['action'] == 'CLOSE_SHORT' and current_sell:
            pnl_pct = (1 - t['price'] / current_sell['price']) * 100
            short_trades.append({**current_sell, 'exit_date': t['date'], 'exit_price': t['price'], 'pnl_pct': pnl_pct})
            current_sell = None
    
    return long_trades, short_trades


if __name__ == '__main__':
    loader = OsEngineLoader()
    
    print('Z-SCORE СТРАТЕГИЯ\n')
    
    for instrument in ['Аэрофлот', 'ЛУКОЙЛ', 'МосБиржа', 'GLDRUBF(вечный)']:
        print(f'{"="*60}')
        print(f'ИНСТРУМЕНТ: {instrument}')
        print(f'{"="*60}')
        
        df_raw = loader.load(instrument)
        df = loader.to_daily(df_raw)
        
        for entry_z in [2.0, 2.5]:
            trades, z = zscore_strategy(df, entry_z=entry_z, exit_z=0.0, sma_period=20)
            long_t, short_t = analyze_trades(trades)
            
            total_trades = len(long_t) + len(short_t)
            
            if total_trades == 0:
                print(f'  Z={entry_z}: 0 сделок')
                continue
            
            long_win = sum(1 for t in long_t if t['pnl_pct'] > 0)
            short_win = sum(1 for t in short_t if t['pnl_pct'] > 0)
            win_rate = 100 * (long_win + short_win) / total_trades
            
            long_pnl = sum(t['pnl_pct'] for t in long_t)
            short_pnl = sum(t['pnl_pct'] for t in short_t)
            total_pnl = long_pnl + short_pnl
            
            print(f'  Z={entry_z}: {len(long_t)}L + {len(short_t)}S = {total_trades} сделок, '
                  f'Win={win_rate:.0f}%, PnL={total_pnl:+.1f}%')
        
        print()
