#!/usr/bin/env python3
"""
Бэктест парного робота: сравнить старую (entry_z=2.0) и новую (entry_z=3.0 + corr) логику.
"""
import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path

DB = Path('/root/finlab/robots/pairs_robot.db')
CANDLES = Path('/root/finlab/data/candles')


def zscore_series(df_a, df_b, window=20):
    """Z-score спреда (log_a - log_b)."""
    _ca = 'begin' if 'begin' in df_a.columns else 'tradedate'
    _cb = 'begin' if 'begin' in df_b.columns else 'tradedate'
    a = df_a[[_ca, 'close']].rename(columns={_ca: 'dt'})
    b = df_b[[_cb, 'close']].rename(columns={_cb: 'dt'})
    m = pd.merge(a, b, on='dt', suffixes=('_a', '_b'))
    m['close_a'] = m['close_a'].apply(lambda x: float(x) if not isinstance(x, bytes) else 0.0)
    m['close_b'] = m['close_b'].apply(lambda x: float(x) if not isinstance(x, bytes) else 0.0)
    spread = np.log(m['close_a']) - np.log(m['close_b'])
    mean = spread.rolling(window).mean()
    std = spread.rolling(window).std()
    return (spread - mean) / std, m


def main():
    conn = sqlite3.connect(DB)
    df = pd.read_sql_query('''
        SELECT id, pair_name, base_pair, timeframe, direction,
               entry_time, exit_time, entry_z, exit_z,
               entry_price_a, entry_price_b, exit_price_a, exit_price_b,
               leg_a_ticker, leg_b_ticker, leg_a_direction, leg_b_direction,
               leg_a_pnl, leg_b_pnl, pnl
        FROM positions
        WHERE status='CLOSED' AND exit_price_a != 0 AND exit_price_b != 0
        ORDER BY id
    ''', conn)
    conn.close()

    print(f'Всего закрытых сделок: {len(df)}')
    print()
    print(f'{"id":<4} {"pair":<18} {"dir":<14} {"entry_z":>8} {"exit_z":>8} {"pnl":>10} {"days":>6}')
    print('-' * 75)

    for _, r in df.iterrows():
        days = None
        if r['entry_time'] and r['exit_time']:
            try:
                d1 = pd.to_datetime(r['entry_time'])
                d2 = pd.to_datetime(r['exit_time'])
                days = (d2 - d1).total_seconds() / 86400
            except:
                pass
        print(f'{r["id"]:<4} {r["pair_name"]:<18} {r["direction"]:<14} '
              f'{r["entry_z"] or 0:>8.2f} {r["exit_z"] or 0:>8.2f} {r["pnl"] or 0:>10.2f} '
              f'{days or 0:>6.2f}')

    # Статистика по группам entry_z
    print()
    print('=== Статистика по группам entry_z ===')
    df['abs_z'] = df['entry_z'].abs()
    for lo, hi, name in [(0, 2, '<2.0'), (2, 2.5, '2.0-2.5'), (2.5, 3, '2.5-3.0'), (3, 10, '>=3.0')]:
        sub = df[(df['abs_z'] >= lo) & (df['abs_z'] < hi)]
        if len(sub) > 0:
            wins = (sub['pnl'] > 0).sum()
            print(f'  {name}: cnt={len(sub)}, wins={wins}, WR={100*wins/len(sub):.1f}%, pnl={sub["pnl"].sum():+.2f}₽')


if __name__ == '__main__':
    main()
