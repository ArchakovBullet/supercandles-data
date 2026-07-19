"""
Renaissance Scanner для акций — сезонность, паттерны на 393 днях данных.
"""
import sys
sys.path.insert(0, '/root/finlab/FinLabPy')
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
import json

DATA = Path('/root/finlab/data')
STOCKS = ['SBER','GAZP','GMKN','LKOH','HYDR','IRAO','AFKS','TATN','VTBR','PLZL','ROSN','T']

def analyze_seasonality_stocks():
    """Сезонность по дням недели для всех акций."""
    weekday_names = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт']
    all_weekdays = {day: [] for day in weekday_names}
    
    for ticker in STOCKS:
        f = DATA / 'candles' / f'{ticker}_D1.parquet'
        if not f.exists():
            continue
        df = pd.read_parquet(f)
        df['date'] = pd.to_datetime(df['begin'])
        df['weekday'] = df['date'].dt.dayofweek
        df['return'] = df['close'].pct_change() * 100
        for day in range(5):
            day_returns = df[(df['weekday'] == day)]['return'].dropna()
            if len(day_returns) > 0:
                all_weekdays[weekday_names[day]].extend(day_returns.tolist())
    
    print("\n=== СЕЗОННОСТЬ АКЦИЙ ===")
    print(f"{'День':8} {'Средняя':>10} {'Win-rate':>10} {'N':>8}")
    print("-" * 40)
    for day in weekday_names:
        returns = all_weekdays[day]
        if returns:
            avg = np.mean(returns)
            win = (np.array(returns) > 0).mean() * 100
            print(f"{day:8} {avg:>+10.2f}% {win:>9.1f}% {len(returns):>8}")

def analyze_supertrend_patterns():
    """Анализ сигналов SuperTrend для акций."""
    print("\n=== SUPERTREND ПАТТЕРНЫ ===")
    
    for ticker in STOCKS[:5]:
        f = DATA / 'candles' / f'{ticker}_D1.parquet'
        if not f.exists():
            continue
        df = pd.read_parquet(f)
        if len(df) < 50:
            continue
        
        # Упрощённый SuperTrend: цена > SMA20 = LONG
        df['sma20'] = df['close'].rolling(20).mean()
        df['signal'] = 'LONG'
        df.loc[df['close'] < df['sma20'], 'signal'] = 'SHORT'
        df['return_5d'] = df['close'].pct_change(5).shift(-5) * 100
        
        long_signals = df[df['signal'] == 'LONG']
        short_signals = df[df['signal'] == 'SHORT']
        
        if len(long_signals) > 10:
            win = (long_signals['return_5d'] > 0).mean() * 100
            print(f"  {ticker}: LONG win={win:.0f}% (n={len(long_signals)})")
        if len(short_signals) > 10:
            win = (short_signals['return_5d'] < 0).mean() * 100
            print(f"  {ticker}: SHORT win={win:.0f}% (n={len(short_signals)})")

def analyze_hi2_patterns():
    """Анализ HI2 для акций."""
    print("\n=== HI2 ПАТТЕРНЫ ===")
    
    for ticker in STOCKS[:5]:
        hi2_file = DATA / 'hi2' / f'{ticker}_hi2.parquet'
        d1_file = DATA / 'candles' / f'{ticker}_D1.parquet'
        if not hi2_file.exists() or not d1_file.exists():
            continue
        
        df_hi2 = pd.read_parquet(hi2_file)
        df_hi2 = df_hi2[df_hi2['metric'] == 'hhi_agressive']
        if len(df_hi2) < 20:
            continue
        
        df_hi2['tradedate'] = pd.to_datetime(df_hi2['tradedate']).dt.date
        
        df_d1 = pd.read_parquet(d1_file)
        df_d1['tradedate'] = pd.to_datetime(df_d1['begin']).dt.date
        
        merged = df_d1.merge(df_hi2[['tradedate','value']].rename(columns={'value':'hi2'}), on='tradedate', how='inner')
        merged['return_5d'] = merged['close'].pct_change(5).shift(-5) * 100
        
        # Высокий HI2 (>500) — предвестник движения?
        high_hi2 = merged[merged['hi2'] > 500]
        if len(high_hi2) > 5:
            avg_ret = high_hi2['return_5d'].mean()
            print(f"  {ticker}: HI2>500 → avg return = {avg_ret:+.2f}% (n={len(high_hi2)})")
        
        # Низкий HI2 (<100) — спокойный рынок?
        low_hi2 = merged[merged['hi2'] < 100]
        if len(low_hi2) > 5:
            avg_ret = low_hi2['return_5d'].mean()
            print(f"  {ticker}: HI2<100 → avg return = {avg_ret:+.2f}% (n={len(low_hi2)})")

def main():
    print("=" * 60)
    print("RENAISSANCE SCANNER — АКЦИИ")
    print(f"Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    analyze_seasonality_stocks()
    analyze_supertrend_patterns()
    analyze_hi2_patterns()

if __name__ == '__main__':
    main()
