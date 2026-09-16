#!/usr/bin/env python3
"""
Тест индивидуального ATR для волатильных тикеров.
MG, GZ, MC, SN, NA — 2.5×ATR (вместо 3.2×ATR).
"""
import sqlite3
import pandas as pd
from pathlib import Path

DB = Path('/root/finlab/robots/futures_robot.db')
CANDLES = Path('/root/finlab/data/candles')

# Индивидуальные множители
ATR_MULT = {
    'MG': 2.5, 'GZ': 2.5, 'MC': 2.5, 'SN': 2.5, 'NA': 2.5,
    'default': 3.2
}
BE_MOVE_ATR = 1.5


def simulate_trade(ticker, direction, entry_time, entry_price, entry_atr, exit_time):
    mult = ATR_MULT.get(ticker, ATR_MULT['default'])
    m10_file = CANDLES / f'{ticker}_M10.parquet'
    if not m10_file.exists():
        return None, None, None

    df = pd.read_parquet(m10_file)
    if 'begin' in df.columns:
        df['dt'] = pd.to_datetime(df['begin'])
    elif 'tradedate' in df.columns and 'tradetime' in df.columns:
        df['dt'] = pd.to_datetime(df['tradedate'] + ' ' + df['tradetime'])
    else:
        return None, None, None

    entry_dt = pd.to_datetime(entry_time)
    exit_dt = pd.to_datetime(exit_time)
    df_trade = df[(df['dt'] >= entry_dt) & (df['dt'] <= exit_dt)].copy()
    if len(df_trade) == 0:
        return None, None, None

    if direction == 'LONG':
        stop_price = entry_price - entry_atr * mult
    else:
        stop_price = entry_price + entry_atr * mult

    breakeven_set = False
    for _, row in df_trade.iterrows():
        high = float(row['high'])
        low = float(row['low'])
        if direction == 'LONG':
            if not breakeven_set and high >= entry_price + entry_atr * BE_MOVE_ATR:
                stop_price = entry_price
                breakeven_set = True
            if low <= stop_price:
                reason = 'BREAKEVEN' if breakeven_set else 'STOP'
                return stop_price, reason, stop_price - entry_price
        else:
            if not breakeven_set and low <= entry_price - entry_atr * BE_MOVE_ATR:
                stop_price = entry_price
                breakeven_set = True
            if high >= stop_price:
                reason = 'BREAKEVEN' if breakeven_set else 'STOP'
                return stop_price, reason, entry_price - stop_price

    last = float(df_trade.iloc[-1]['close'])
    return last, 'SIGNAL', (last - entry_price) if direction == 'LONG' else (entry_price - last)


def main():
    conn = sqlite3.connect(DB)
    df = pd.read_sql_query('''
        SELECT id, ticker, direction, entry_time, entry_price, entry_atr, 
               exit_time, exit_price, exit_reason, pnl, point_value
        FROM futures_positions 
        WHERE status='CLOSED' AND exit_reason IN ('STOP', 'SIGNAL', 'BREAKEVEN')
        ORDER BY id
    ''', conn)
    conn.close()

    print(f'{"id":<4} {"ticker":<8} {"old":>10} {"2.5x":>10} {"3.2x":>10} {"diff":>10}')
    print('-' * 60)

    old_total = 0
    new_25_total = 0
    new_32_total = 0

    for _, row in df.iterrows():
        old_pnl = row['pnl'] or 0
        pv = row['point_value'] or 1.0
        ticker = row['ticker']

        # 2.5x
        _, _, p25 = simulate_trade(ticker, row['direction'], row['entry_time'],
                                     row['entry_price'], row['entry_atr'], row['exit_time'])
        # 3.2x — временно меняем ATR_MULT
        saved = ATR_MULT.get(ticker, ATR_MULT['default'])
        ATR_MULT[ticker] = 3.2
        _, _, p32 = simulate_trade(ticker, row['direction'], row['entry_time'],
                                     row['entry_price'], row['entry_atr'], row['exit_time'])
        ATR_MULT[ticker] = saved

        p25 = p25 * pv if p25 is not None else old_pnl
        p32 = p32 * pv if p32 is not None else old_pnl

        old_total += old_pnl
        new_25_total += p25
        new_32_total += p32

        if ticker in ['MG', 'GZ', 'MC', 'SN', 'NA', 'HS', 'RL', 'CE', 'GD']:
            print(f'{row["id"]:<4} {ticker:<8} {old_pnl:>10.2f} {p25:>10.2f} {p32:>10.2f} {p25 - p32:>+10.2f}')

    print('-' * 60)
    print(f'{"ИТОГО":<12} {old_total:>10.2f} {new_25_total:>10.2f} {new_32_total:>10.2f}')
    print()
    print(f'Старый:        {old_total:+.2f}₽')
    print(f'Новый 2.5×ATR: {new_25_total:+.2f}₽')
    print(f'Новый 3.2×ATR: {new_32_total:+.2f}₽')


if __name__ == '__main__':
    main()
