#!/usr/bin/env python3
"""
Бэктест стопов: сравнить старую логику (2×ATR) с новой (3.2×ATR + безубыток).
Для каждой закрытой сделки из БД — прогнать M10-данные.
"""
import sqlite3
import pandas as pd
from pathlib import Path
from datetime import datetime

DB = Path('/root/finlab/robots/futures_robot.db')
CANDLES = Path('/root/finlab/data/candles')

STOP_ATR_MULT = 3.2
BE_MOVE_ATR = 1.5


def simulate_trade(ticker, direction, entry_time, entry_price, entry_atr, exit_time):
    """
    Симулировать сделку с новой логикой стопов.
    Возвращает: (exit_price, exit_reason, pnl_points)
    """
    m10_file = CANDLES / f'{ticker}_M10.parquet'
    if not m10_file.exists():
        return None, None, None
    
    # Проверка на nan в входных данных
    if entry_price != entry_price or entry_atr != entry_atr:
        return None, None, None

    df = pd.read_parquet(m10_file)
    
    # Определяем колонку с датой
    if 'begin' in df.columns:
        df['dt'] = pd.to_datetime(df['begin'])
    elif 'tradedate' in df.columns and 'tradetime' in df.columns:
        df['dt'] = pd.to_datetime(df['tradedate'] + ' ' + df['tradetime'])
    elif 'tradedate' in df.columns:
        df['dt'] = pd.to_datetime(df['tradedate'])
    else:
        return None, None, None

    # Фильтруем по времени сделки
    entry_dt = pd.to_datetime(entry_time)
    exit_dt = pd.to_datetime(exit_time)

    df_trade = df[(df['dt'] >= entry_dt) & (df['dt'] <= exit_dt)].copy()
    if len(df_trade) == 0:
        return None, None, None

    # Начальный стоп
    if direction == 'LONG':
        stop_price = entry_price - entry_atr * STOP_ATR_MULT
    else:
        stop_price = entry_price + entry_atr * STOP_ATR_MULT

    breakeven_set = False

    for _, row in df_trade.iterrows():
        high = float(row['high'])
        low = float(row['low'])

        if direction == 'LONG':
            # Проверяем безубыток
            if not breakeven_set and high >= entry_price + entry_atr * BE_MOVE_ATR:
                stop_price = entry_price
                breakeven_set = True

            # Проверяем стоп
            if low <= stop_price:
                reason = 'BREAKEVEN' if breakeven_set else 'STOP'
                pnl_points = (stop_price - entry_price)
                return stop_price, reason, pnl_points
        else:  # SHORT
            if not breakeven_set and low <= entry_price - entry_atr * BE_MOVE_ATR:
                stop_price = entry_price
                breakeven_set = True

            if high >= stop_price:
                reason = 'BREAKEVEN' if breakeven_set else 'STOP'
                pnl_points = (entry_price - stop_price)
                return stop_price, reason, pnl_points

    # Если не закрылось по стопу — берём последнюю цену
    last_price = float(df_trade.iloc[-1]['close'])
    if direction == 'LONG':
        pnl_points = (last_price - entry_price)
    else:
        pnl_points = (entry_price - last_price)
    
    # Проверка на nan
    if pnl_points != pnl_points:  # nan check
        return None, None, None
    
    return last_price, 'SIGNAL', pnl_points


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

    print(f'Всего сделок: {len(df)}')
    print()

    old_total = 0
    new_total = 0

    print(f'{"id":<4} {"ticker":<8} {"dir":<6} {"old_pnl":>10} {"new_pnl":>10} {"diff":>10} {"old_r":<8} {"new_r":<10}')
    print('-' * 80)

    for _, row in df.iterrows():
        old_pnl = row['pnl'] or 0
        pv = row['point_value'] if pd.notna(row['point_value']) else 1.0

        new_exit, new_reason, new_points = simulate_trade(
            row['ticker'], row['direction'], row['entry_time'],
            row['entry_price'], row['entry_atr'], row['exit_time']
        )

        if new_points is None:
            print(f'{row["id"]:<4} {row["ticker"]:<8} {row["direction"]:<6} {old_pnl:>10.2f} {"SKIP":>10} {"—":>10} {row["exit_reason"]:<8} {"NO_DATA":<10}')
            old_total += old_pnl
            new_total += old_pnl  # считаем как старый (нет данных)
            continue

        new_pnl = new_points * pv
        diff = new_pnl - old_pnl

        old_total += old_pnl
        new_total += new_pnl

        print(f'{row["id"]:<4} {row["ticker"]:<8} {row["direction"]:<6} {old_pnl:>10.2f} {new_pnl:>10.2f} {diff:>+10.2f} {row["exit_reason"]:<8} {new_reason:<10}')

    print('-' * 80)
    print(f'{"ИТОГО":<20} {old_total:>10.2f} {new_total:>10.2f} {new_total - old_total:>+10.2f}')
    print()
    print(f'Старый PnL: {old_total:+.2f}₽')
    print(f'Новый PnL:  {new_total:+.2f}₽')
    print(f'Разница:    {new_total - old_total:+.2f}₽')

    # Разбивка по тикерам
    print()
    print('=== Разбивка по тикерам ===')
    by_ticker = {}
    for _, row in df.iterrows():
        old_pnl = row['pnl'] or 0
        pv = row['point_value'] if pd.notna(row['point_value']) else 1.0
        new_exit, new_reason, new_points = simulate_trade(
            row['ticker'], row['direction'], row['entry_time'],
            row['entry_price'], row['entry_atr'], row['exit_time']
        )
        if new_points is None:
            new_pnl = old_pnl
        else:
            new_pnl = new_points * pv
        t = row['ticker']
        if t not in by_ticker:
            by_ticker[t] = [0, 0, 0]
        by_ticker[t][0] += old_pnl
        by_ticker[t][1] += new_pnl
        by_ticker[t][2] += 1
    
    print(f'{"ticker":<10} {"cnt":>4} {"old_pnl":>10} {"new_pnl":>10} {"diff":>10}')
    print('-' * 50)
    for t, (old, new, cnt) in sorted(by_ticker.items(), key=lambda x: x[1][1] - x[1][0]):
        print(f'{t:<10} {cnt:>4} {old:>10.2f} {new:>10.2f} {new - old:>+10.2f}')


if __name__ == '__main__':
    main()
