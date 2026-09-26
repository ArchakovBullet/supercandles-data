#!/usr/bin/env python3
"""
analyze_imbalance.py

Анализ рыночных данных: дисбаланс (FutOI + TradeStats) → forward return цены.

Цель: проверить гипотезу — предсказывает ли дисбаланс (давление юрлиц vs физлиц)
движение цены на 1ч / 4ч / 1д / 3д вперёд.

Данные:
  - FutOI 1h: yur_buy_ratio, fiz_buy_ratio
  - TradeStats: disb (агрегируется до часа — mean)
  - Цены H1: close

Тикеры: GAZPF, SBERF, GLDRUBF, USDRUBF, CNYRUBF, EURRUBF

Вывод: data/analyze_imbalance_results.csv + сводка в терминал
"""

import pandas as pd
import numpy as np
from pathlib import Path

# === Конфигурация ===
TICKERS = ['GAZPF', 'SBERF', 'GLDRUBF', 'USDRUBF', 'CNYRUBF', 'EURRUBF']
FUTOI_FILE = 'data/futoi_1h/futoi_1h.parquet'
CANDLES_DIR = 'data/candles'
TRADESTATS_DIR = 'data/tradestats'
OUTPUT_CSV = 'data/analyze_imbalance_results.csv'

# Forward return горизонты (в часах H1)
FWD_HORIZONS = {'fwd_1h': 1, 'fwd_4h': 4, 'fwd_1d': 24, 'fwd_3d': 72}


def load_futoi(ticker):
    """Загрузка FutOI 1h по тикеру."""
    df = pd.read_parquet(FUTOI_FILE)
    sub = df[df['ticker'] == ticker].copy()
    sub['hour'] = pd.to_datetime(sub['hour'])
    sub = sub[['hour', 'yur_buy_ratio', 'fiz_buy_ratio']].copy()
    sub = sub.dropna(subset=['yur_buy_ratio', 'fiz_buy_ratio'])
    return sub


def load_tradestats_hourly(ticker):
    """Загрузка TradeStats, агрегация disb до часа."""
    path = Path(TRADESTATS_DIR) / f'{ticker}_tradestats.parquet'
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    df['tradedate'] = pd.to_datetime(df['tradedate'])
    df['dt'] = df['tradedate'] + pd.to_timedelta(df['tradetime'])
    df['hour'] = df['dt'].dt.floor('h')
    # Агрегация: средний disb за час
    agg = df.groupby('hour')['disb'].mean().reset_index()
    agg = agg.rename(columns={'disb': 'disb_hourly'})
    return agg


def load_prices_h1(ticker):
    """Загрузка цен H1 по тикеру."""
    path = Path(CANDLES_DIR) / f'{ticker}_H1.parquet'
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    df['begin'] = pd.to_datetime(df['begin'])
    df = df[['begin', 'close']].copy()
    df = df.sort_values('begin').reset_index(drop=True)
    return df


def merge_sources(ticker):
    """Мерж FutOI + TradeStats + цены по часу."""
    futoi = load_futoi(ticker)
    ts = load_tradestats_hourly(ticker)
    prices = load_prices_h1(ticker)
    if prices is None:
        return None

    # Мерж FutOI + prices
    df = pd.merge(futoi, prices, left_on='hour', right_on='begin', how='inner')
    # Мерж с TradeStats (если есть)
    if ts is not None:
        df = pd.merge(df, ts, on='hour', how='left')
    else:
        df['disb_hourly'] = np.nan

    df = df.sort_values('hour').reset_index(drop=True)
    return df


def compute_imbalance(df):
    """
    Составной индикатор дисбаланса.
    > 0 — юрлица покупают, физлица продают (бычий).
    < 0 — наоборот (медвежий).
    Нормировано примерно в [-2, +2].
    """
    yur = (df['yur_buy_ratio'] - 50.0) / 50.0   # -1 .. +1
    fiz = (df['fiz_buy_ratio'] - 50.0) / 50.0   # -1 .. +1
    imbalance = yur - fiz                        # -2 .. +2
    return imbalance


def compute_forward_returns(df):
    """Считает forward return для каждого горизонта."""
    for name, hours in FWD_HORIZONS.items():
        df[name] = (df['close'].shift(-hours) - df['close']) / df['close']
    return df


def analyze_ticker(ticker):
    """Полный анализ одного тикера."""
    df = merge_sources(ticker)
    if df is None or len(df) < 100:
        print(f'  {ticker}: данных мало ({len(df) if df is not None else 0}), пропуск')
        return None

    df['imbalance'] = compute_imbalance(df)
    df = compute_forward_returns(df)

    # Метки
    df['ticker'] = ticker
    df['date'] = df['hour'].dt.date

    # Оставляем только строки с forward returns (без NaN)
    valid = df.dropna(subset=list(FWD_HORIZONS.keys())).copy()

    print(f'  {ticker}: {len(df)} часов, {len(valid)} с fwd_return, '
          f'период {df["hour"].min()} — {df["hour"].max()}')

    return valid


def summarize(all_df):
    """Сводный анализ по всем тикерам."""
    print('\n' + '=' * 70)
    print('СВОДНЫЙ АНАЛИЗ: дисбаланс → forward return')
    print('=' * 70)

    # Корреляции
    print('\n--- Корреляции imbalance ↔ forward return (Pearson) ---')
    for fwd in FWD_HORIZONS:
        sub = all_df.dropna(subset=['imbalance', fwd])
        if len(sub) > 10:
            corr_p = sub['imbalance'].corr(sub[fwd], method='pearson')
            corr_s = sub['imbalance'].corr(sub[fwd], method='spearman')
            print(f'  {fwd}: Pearson={corr_p:+.4f}, Spearman={corr_s:+.4f}, n={len(sub)}')

    # Win Rate по группам
    print('\n--- Win Rate по группам дисбаланса ---')
    print(f'{"Группа":<25} {"n":>6} {"fwd_1h":>10} {"fwd_4h":>10} {"fwd_1d":>10} {"fwd_3d":>10}')
    groups = [
        ('strong_bull (>0.3)', all_df[all_df['imbalance'] > 0.3]),
        ('mild_bull (0.1..0.3)', all_df[(all_df['imbalance'] > 0.1) & (all_df['imbalance'] <= 0.3)]),
        ('neutral (-0.1..0.1)', all_df[all_df['imbalance'].abs() <= 0.1]),
        ('mild_bear (-0.3..-0.1)', all_df[(all_df['imbalance'] < -0.1) & (all_df['imbalance'] >= -0.3)]),
        ('strong_bear (<-0.3)', all_df[all_df['imbalance'] < -0.3]),
    ]
    for name, g in groups:
        if len(g) > 0:
            row = [f'{name:<25}', f'{len(g):>6}']
            for fwd in FWD_HORIZONS:
                row.append(f'{g[fwd].mean():>+10.5f}')
            print(' '.join(row))

    # Win Rate (направление): imbalance > 0 → цена вверх?
    print('\n--- Win Rate (направление угадано) ---')
    for fwd in FWD_HORIZONS:
        sub = all_df.dropna(subset=['imbalance', fwd])
        if len(sub) < 10:
            continue
        bull = sub[sub['imbalance'] > 0.3]
        bear = sub[sub['imbalance'] < -0.3]
        if len(bull) > 0:
            wr_bull = (bull[fwd] > 0).mean()
        else:
            wr_bull = float('nan')
        if len(bear) > 0:
            wr_bear = (bear[fwd] < 0).mean()
        else:
            wr_bear = float('nan')
        print(f'  {fwd}: bull(>0.3) WR={wr_bull:.3f} (n={len(bull)}), '
              f'bear(<-0.3) WR={wr_bear:.3f} (n={len(bear)})')

    # По тикерам
    print('\n--- По тикерам (корреляция imbalance ↔ fwd_4h) ---')
    for t in sorted(all_df['ticker'].unique()):
        sub = all_df[all_df['ticker'] == t].dropna(subset=['imbalance', 'fwd_4h'])
        if len(sub) > 10:
            corr = sub['imbalance'].corr(sub['fwd_4h'], method='spearman')
            print(f'  {t:<10}: Spearman={corr:+.4f}, n={len(sub)}')


def main():
    print('=' * 70)
    print('analyze_imbalance.py — дисбаланс → forward return')
    print('=' * 70)

    all_dfs = []
    for ticker in TICKERS:
        print(f'\nОбработка {ticker}...')
        df = analyze_ticker(ticker)
        if df is not None and len(df) > 0:
            all_dfs.append(df)

    if not all_dfs:
        print('Нет данных для анализа')
        return

    all_df = pd.concat(all_dfs, ignore_index=True)
    print(f'\nВсего строк: {len(all_df)}')

    # Сохраняем
    all_df.to_parquet(OUTPUT_CSV.replace('.csv', '.parquet'), index=False)
    all_df.to_csv(OUTPUT_CSV, index=False)
    print(f'Сохранено: {OUTPUT_CSV}')

    # Анализ
    summarize(all_df)

    print('\n' + '=' * 70)
    print('Готово.')
    print('=' * 70)


if __name__ == '__main__':
    main()
