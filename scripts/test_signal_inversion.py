#!/usr/bin/env python3
"""
Тест инверсии сигналов: если бы вошли в обратную сторону.
"""
import sqlite3
import pandas as pd
from pathlib import Path

DB = Path('/root/finlab/robots/futures_robot.db')
CANDLES = Path('/root/finlab/data/candles')


def analyze_trade(ticker, direction, entry_time, entry_price, exit_time):
    m10_file = CANDLES / f'{ticker}_M10.parquet'
    if not m10_file.exists():
        return None
    df = pd.read_parquet(m10_file)
    if 'begin' in df.columns:
        df['dt'] = pd.to_datetime(df['begin'])
    elif 'tradedate' in df.columns and 'tradetime' in df.columns:
        df['dt'] = pd.to_datetime(df['tradedate'] + ' ' + df['tradetime'])
    else:
        return None
    entry_dt = pd.to_datetime(entry_time)
    df_after = df[df['dt'] >= entry_dt].copy()
    if len(df_after) == 0:
        return None
    if direction == 'LONG':
        mf = (df_after['high'].max() - entry_price)
        ma = (entry_price - df_after['low'].min())
    else:
        mf = (entry_price - df_after['low'].min())
        ma = (df_after['high'].max() - entry_price)
    return mf, ma


def main():
    conn = sqlite3.connect(DB)
    df = pd.read_sql_query('''
        SELECT id, ticker, direction, entry_time, entry_price, exit_time, 
               exit_reason, pnl, point_value, entry_score
        FROM futures_positions 
        WHERE status='CLOSED' AND exit_reason IN ('STOP', 'SIGNAL', 'BREAKEVEN', 'EXPIRY_MANUAL')
        ORDER BY id
    ''', conn)
    conn.close()

    print(f'{"id":<4} {"ticker":<8} {"dir":<6} {"score":>5} {"pnl":>10} {"mf":>8} {"ma":>8} {"inv_pnl":>10} {"better":<8}')
    print('-' * 80)

    normal_wins = 0
    inverted_wins = 0
    normal_total = 0
    inverted_total = 0

    for _, row in df.iterrows():
        result = analyze_trade(row['ticker'], row['direction'], row['entry_time'],
                                row['entry_price'], row['exit_time'])
        if result is None:
            continue
        mf, ma = result
        pv = row['point_value'] or 1.0
        pnl = row['pnl'] or 0

        # Инвертированный PnL: если бы шли в обратную сторону
        # mf (favorable) становится adverse, ma — favorable
        inv_pnl = ma * pv  # по max_adverse (в нашу сторону при инверсии)
        # Более реалистично: инвертированный стоп сработал бы по mf
        inv_pnl_realistic = -mf * pv

        if mf > ma:
            normal_wins += 1
        else:
            inverted_wins += 1
        normal_total += pnl
        inverted_total += inv_pnl_realistic

        better = 'INV' if ma > mf else 'NORM'
        print(f'{row["id"]:<4} {row["ticker"]:<8} {row["direction"]:<6} {row["entry_score"] or 0:>5.0f} {pnl:>10.2f} {mf:>8.2f} {ma:>8.2f} {inv_pnl_realistic:>10.2f} {better:<8}')

    print('-' * 80)
    print(f'Normal wins (mf>ma):   {normal_wins}')
    print(f'Inverted wins (ma>mf): {inverted_wins}')
    print(f'Normal total PnL:      {normal_total:+.2f}₽')
    print(f'Inverted total PnL:    {inverted_total:+.2f}₽')
    print()
    if inverted_wins > normal_wins:
        print(f'⚠️ ИНВЕРСИЯ: сигналы работают ПРОТИВ нас ({inverted_wins} vs {normal_wins})')
    else:
        print(f'✅ Сигналы работают В НАШУ сторону ({normal_wins} vs {inverted_wins})')


if __name__ == '__main__':
    main()
