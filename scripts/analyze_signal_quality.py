#!/usr/bin/env python3
"""
Анализ качества сигналов: куда пошла цена после входа.
Для каждой сделки:
- entry_price, direction
- max_favorable (максимум в нашу сторону)
- max_adverse (максимум против нас)
- через 1ч, 4ч, 1д после входа
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
    exit_dt = pd.to_datetime(exit_time)

    df_after = df[df['dt'] >= entry_dt].copy()
    if len(df_after) == 0:
        return None

    # Максимум в нашу сторону и против
    if direction == 'LONG':
        max_favorable = (df_after['high'].max() - entry_price)
        max_adverse = (entry_price - df_after['low'].min())
    else:
        max_favorable = (entry_price - df_after['low'].min())
        max_adverse = (df_after['high'].max() - entry_price)

    # Через 1ч, 4ч, 1д
    def price_at(hours):
        target = entry_dt + pd.Timedelta(hours=hours)
        df_at = df_after[df_after['dt'] <= target]
        if len(df_at) == 0:
            return None
        return float(df_at.iloc[-1]['close'])

    p1h = price_at(1)
    p4h = price_at(4)
    p1d = price_at(24)

    return {
        'max_favorable': max_favorable,
        'max_adverse': max_adverse,
        'p1h': p1h,
        'p4h': p4h,
        'p1d': p1d,
    }


def main():
    conn = sqlite3.connect(DB)
    df = pd.read_sql_query('''
        SELECT id, ticker, direction, entry_time, entry_price, entry_atr, 
               exit_time, exit_price, exit_reason, pnl, point_value, entry_score
        FROM futures_positions 
        WHERE status='CLOSED' AND exit_reason IN ('STOP', 'SIGNAL', 'BREAKEVEN', 'EXPIRY_MANUAL')
        ORDER BY id
    ''', conn)
    conn.close()

    print(f'{"id":<4} {"ticker":<8} {"dir":<6} {"score":>6} {"pnl":>10} {"max_fav":>10} {"max_adv":>10} {"p1h":>10} {"p4h":>10} {"p1d":>10} {"r":<8}')
    print('-' * 110)

    favorable_count = 0
    adverse_count = 0

    for _, row in df.iterrows():
        result = analyze_trade(row['ticker'], row['direction'], row['entry_time'],
                                row['entry_price'], row['exit_time'])
        if result is None:
            continue

        pv = row['point_value'] or 1.0
        mf = result['max_favorable']
        ma = result['max_adverse']

        # Определяем, было ли движение в нашу сторону
        if mf > ma:
            favorable_count += 1
        else:
            adverse_count += 1

        # Через 1ч, 4ч, 1д — в пунктах
        def delta(p):
            if p is None:
                return None
            if row['direction'] == 'LONG':
                return (p - row['entry_price'])
            else:
                return (row['entry_price'] - p)

        d1h = delta(result['p1h'])
        d4h = delta(result['p4h'])
        d1d = delta(result['p1d'])

        print(f'{row["id"]:<4} {row["ticker"]:<8} {row["direction"]:<6} {row["entry_score"] or 0:>6.0f} {row["pnl"] or 0:>10.2f} {mf:>10.2f} {ma:>10.2f} {d1h if d1h is not None else "—":>10} {d4h if d4h is not None else "—":>10} {d1d if d1d is not None else "—":>10} {row["exit_reason"]:<8}')

    print('-' * 110)
    print(f'В нашу сторону: {favorable_count}')
    print(f'Против нас: {adverse_count}')
    print(f'Win Rate (по max_favorable): {100.0 * favorable_count / (favorable_count + adverse_count):.1f}%')


if __name__ == '__main__':
    main()
