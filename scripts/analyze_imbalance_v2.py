#!/usr/bin/env python3
"""
analyze_imbalance_v2.py

Подход Джима Саймонса: сначала данные, потом метрика.

Открытия из v1:
  1. yur_buy_ratio и fiz_buy_ratio — почти идеально отрицательно скоррелированы
     (corr от -0.45 до -0.97). Это ОДНА переменная, не две.
  2. У каждого тикера свой базовый уровень yur_buy_ratio (от 9.75 до 46.09).
     Сравнивать между тикерами нельзя.
  3. imbalance = (yur-50)/50 - (fiz-50)/50 — почти всегда отрицательный
     (mean=-1.01). Это структура рынка, не отклонение.

Решение:
  - Использовать ТОЛЬКО yur_buy_ratio (институциональный поток).
  - Нормировать через z-score по скользящему окну (30 дней).
  - Проверить также yur_ratio_delta (изменение за час).
  - Проверить disb (TradeStats) — независимый источник.
"""

import pandas as pd
import numpy as np
from pathlib import Path

TICKERS = ['GAZPF', 'SBERF', 'GLDRUBF', 'USDRUBF', 'CNYRUBF', 'EURRUBF']
FUTOI_FILE = 'data/futoi_1h/futoi_1h.parquet'
CANDLES_DIR = 'data/candles'
TRADESTATS_DIR = 'data/tradestats'
OUTPUT_CSV = 'data/analyze_imbalance_v2_results.csv'

FWD_HORIZONS = {'fwd_1h': 1, 'fwd_4h': 4, 'fwd_1d': 24, 'fwd_3d': 72}
ZSCORE_WINDOW = 720  # часов ~ 30 дней торгов


def load_futoi(ticker):
    df = pd.read_parquet(FUTOI_FILE)
    sub = df[df['ticker'] == ticker].copy()
    sub['hour'] = pd.to_datetime(sub['hour'])
    sub = sub[['hour', 'yur_buy_ratio', 'fiz_buy_ratio',
               'yur_ratio_delta', 'fiz_ratio_delta']].copy()
    sub = sub.dropna(subset=['yur_buy_ratio'])
    return sub.sort_values('hour').reset_index(drop=True)


def load_tradestats_hourly(ticker):
    path = Path(TRADESTATS_DIR) / f'{ticker}_tradestats.parquet'
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    df['tradedate'] = pd.to_datetime(df['tradedate'])
    df['dt'] = df['tradedate'] + pd.to_timedelta(df['tradetime'])
    df['hour'] = df['dt'].dt.floor('h')
    agg = df.groupby('hour')['disb'].mean().reset_index()
    agg = agg.rename(columns={'disb': 'disb_hourly'})
    return agg


def load_prices_h1(ticker):
    path = Path(CANDLES_DIR) / f'{ticker}_H1.parquet'
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    df['begin'] = pd.to_datetime(df['begin'])
    df = df[['begin', 'close']].copy().sort_values('begin').reset_index(drop=True)
    return df


def merge_sources(ticker):
    futoi = load_futoi(ticker)
    ts = load_tradestats_hourly(ticker)
    prices = load_prices_h1(ticker)
    if prices is None:
        return None

    df = pd.merge(futoi, prices, left_on='hour', right_on='begin', how='inner')
    if ts is not None:
        df = pd.merge(df, ts, on='hour', how='left')
    else:
        df['disb_hourly'] = np.nan

    df = df.sort_values('hour').reset_index(drop=True)
    return df


def add_zscore(df):
    """Z-score yur_buy_ratio по скользящему окну."""
    rolling = df['yur_buy_ratio'].rolling(window=ZSCORE_WINDOW, min_periods=100)
    df['yur_z'] = (df['yur_buy_ratio'] - rolling.mean()) / rolling.std()
    # То же для disb (по скользящему окну)
    rolling_d = df['disb_hourly'].rolling(window=ZSCORE_WINDOW, min_periods=100)
    df['disb_z'] = (df['disb_hourly'] - rolling_d.mean()) / rolling_d.std()
    return df


def compute_forward_returns(df):
    for name, hours in FWD_HORIZONS.items():
        df[name] = (df['close'].shift(-hours) - df['close']) / df['close']
    return df


def analyze_ticker(ticker):
    df = merge_sources(ticker)
    if df is None or len(df) < 200:
        print(f'  {ticker}: мало данных ({len(df) if df is not None else 0}), пропуск')
        return None

    df = add_zscore(df)
    df = compute_forward_returns(df)
    df['ticker'] = ticker

    valid = df.dropna(subset=list(FWD_HORIZONS.keys()) + ['yur_z']).copy()
    print(f'  {ticker}: {len(df)} часов, {len(valid)} с fwd+z, '
          f'период {df["hour"].min()} — {df["hour"].max()}')
    return valid


def summarize(all_df):
    print('\n' + '=' * 70)
    print('АНАЛИЗ v2: z-score yur_buy_ratio → forward return')
    print('=' * 70)

    print('\n--- Корреляции yur_z ↔ forward return ---')
    for fwd in FWD_HORIZONS:
        sub = all_df.dropna(subset=['yur_z', fwd])
        if len(sub) > 10:
            p = sub['yur_z'].corr(sub[fwd], method='pearson')
            s = sub['yur_z'].corr(sub[fwd], method='spearman')
            print(f'  {fwd}: Pearson={p:+.4f}, Spearman={s:+.4f}, n={len(sub)}')

    print('\n--- Корреляции yur_ratio_delta ↔ forward return ---')
    for fwd in FWD_HORIZONS:
        sub = all_df.dropna(subset=['yur_ratio_delta', fwd])
        if len(sub) > 10:
            p = sub['yur_ratio_delta'].corr(sub[fwd], method='pearson')
            s = sub['yur_ratio_delta'].corr(sub[fwd], method='spearman')
            print(f'  {fwd}: Pearson={p:+.4f}, Spearman={s:+.4f}, n={len(sub)}')

    print('\n--- Корреляции disb_z ↔ forward return ---')
    for fwd in FWD_HORIZONS:
        sub = all_df.dropna(subset=['disb_z', fwd])
        if len(sub) > 10:
            p = sub['disb_z'].corr(sub[fwd], method='pearson')
            s = sub['disb_z'].corr(sub[fwd], method='spearman')
            print(f'  {fwd}: Pearson={p:+.4f}, Spearman={s:+.4f}, n={len(sub)}')

    # Корреляции между факторами (независимы ли)
    print('\n--- Корреляции между факторами ---')
    factors = ['yur_z', 'disb_z', 'yur_ratio_delta']
    corr = all_df[factors].corr()
    print(corr.to_string())

    # Win Rate по группам yur_z
    print('\n--- Win Rate по группам yur_z ---')
    groups = [
        ('yur_z > +2', all_df[all_df['yur_z'] > 2]),
        ('yur_z 1..2', all_df[(all_df['yur_z'] > 1) & (all_df['yur_z'] <= 2)]),
        ('yur_z -1..1', all_df[all_df['yur_z'].abs() <= 1]),
        ('yur_z -2..-1', all_df[(all_df['yur_z'] < -1) & (all_df['yur_z'] >= -2)]),
        ('yur_z < -2', all_df[all_df['yur_z'] < -2]),
    ]
    print(f'{"Группа":<20} {"n":>6} {"fwd_1h":>10} {"fwd_4h":>10} {"fwd_1d":>10} {"fwd_3d":>10}')
    for name, g in groups:
        if len(g) > 0:
            row = [f'{name:<20}', f'{len(g):>6}']
            for fwd in FWD_HORIZONS:
                row.append(f'{g[fwd].mean():>+10.5f}')
            print(' '.join(row))

    print('\n--- Win Rate (направление) ---')
    for fwd in FWD_HORIZONS:
        sub = all_df.dropna(subset=['yur_z', fwd])
        bull = sub[sub['yur_z'] > 2]
        bear = sub[sub['yur_z'] < -2]
        if len(bull) > 0:
            wr_bull = (bull[fwd] > 0).mean()
        else:
            wr_bull = float('nan')
        if len(bear) > 0:
            wr_bear = (bear[fwd] < 0).mean()
        else:
            wr_bear = float('nan')
        print(f'  {fwd}: bull(>2) WR={wr_bull:.3f} (n={len(bull)}), '
              f'bear(<-2) WR={wr_bear:.3f} (n={len(bear)})')

    print('\n--- По тикерам (yur_z ↔ fwd_4h, Spearman) ---')
    for t in sorted(all_df['ticker'].unique()):
        sub = all_df[all_df['ticker'] == t].dropna(subset=['yur_z', 'fwd_4h'])
        if len(sub) > 10:
            s = sub['yur_z'].corr(sub['fwd_4h'], method='spearman')
            print(f'  {t:<10}: {s:+.4f}, n={len(sub)}')


def main():
    print('=' * 70)
    print('analyze_imbalance_v2.py — z-score yur_buy_ratio → forward return')
    print('=' * 70)

    all_dfs = []
    for ticker in TICKERS:
        print(f'\nОбработка {ticker}...')
        df = analyze_ticker(ticker)
        if df is not None and len(df) > 0:
            all_dfs.append(df)

    if not all_dfs:
        print('Нет данных')
        return

    all_df = pd.concat(all_dfs, ignore_index=True)
    print(f'\nВсего строк: {len(all_df)}')

    all_df.to_parquet(OUTPUT_CSV.replace('.csv', '.parquet'), index=False)
    all_df.to_csv(OUTPUT_CSV, index=False)
    print(f'Сохранено: {OUTPUT_CSV}')

    summarize(all_df)

    print('\n' + '=' * 70)
    print('Готово.')
    print('=' * 70)


if __name__ == '__main__':
    main()
