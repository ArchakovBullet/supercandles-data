#!/usr/bin/env python3
"""
A/B тест unified_scanner: сравнить 4 версии.
- baseline: без disb, HI2, yur
- +disb: с disb
- +disb+hi2: с disb + HI2
- +full: с disb + HI2 + yur
"""
import sys
import json
import pandas as pd
from pathlib import Path

sys.path.insert(0, '/root/finlab/FinLabPy')

from My_Indicators.unified_scanner import get_unified_scanner_verdict

ROOT = Path('/root/finlab')
DATA = ROOT / 'data' / 'candles'
H2 = ROOT / 'data' / 'hi2'
TS = ROOT / 'data' / 'tradestats'
FUTOI_4H = ROOT / 'data' / 'futoi_4h' / 'futoi_4h.parquet'
FUTOI_1H = ROOT / 'data' / 'futoi_1h' / 'futoi_1h.parquet'


def load_signals():
    try:
        with open(ROOT / 'robots' / 'signal_direction.json') as f:
            return json.load(f)
    except Exception:
        return {}


def get_disb(ticker):
    f = TS / f'{ticker}_tradestats.parquet'
    if not f.exists():
        return None
    try:
        df = pd.read_parquet(f)
        if len(df) == 0:
            return None
        val = df.iloc[-1].get('disb')
        return float(val) if pd.notna(val) else None
    except Exception:
        return None


def get_hi2(ticker):
    f = H2 / f'{ticker}_hi2.parquet'
    if not f.exists():
        return None
    try:
        df = pd.read_parquet(f)
        if len(df) == 0:
            return None
        val = df.iloc[-1].get('hhi_agressive')
        return float(val) if pd.notna(val) else None
    except Exception:
        return None


def get_yur(ticker, sd):
    d = sd.get(ticker, sd.get('default', {}))
    return d.get('dir'), d.get('median'), d.get('std')


def load_candles_with_futoi(ticker, tf):
    """Загрузить свечи + merge FutOI (fiz_buy_ratio, yur_buy_ratio)."""
    f = DATA / f'{ticker}_{tf}.parquet'
    if not f.exists():
        return None
    df = pd.read_parquet(f)

    # H4 — tradedate + block
    if tf == 'H4' and 'tradedate' in df.columns and 'block' in df.columns:
        df['dt_full'] = pd.to_datetime(df['tradedate'].astype(str) + ' ' + df['block'].astype(str))
    else:
        if 'begin' in df.columns:
            df['dt_full'] = pd.to_datetime(df['begin'])
        elif 'tradedate' in df.columns:
            df['dt_full'] = pd.to_datetime(df['tradedate'])

    # Merge FutOI
    futoi_file = FUTOI_4H if tf == 'H4' else (FUTOI_1H if tf == 'H1' else None)
    if futoi_file and futoi_file.exists():
        try:
            futoi = pd.read_parquet(futoi_file)
            futoi_t = futoi[futoi['ticker'] == ticker].copy()
            if len(futoi_t) > 0:
                futoi_t['dt_full'] = pd.to_datetime(futoi_t['hour'])
                df = pd.merge_asof(
                    df.sort_values('dt_full'),
                    futoi_t[['dt_full', 'fiz_buy_ratio', 'yur_buy_ratio']].sort_values('dt_full'),
                    on='dt_full', direction='backward'
                )
                df = df.ffill()
        except Exception as e:
            pass

    # D1 — берём последнее значение из H4
    if tf == 'D1' and FUTOI_4H.exists():
        try:
            futoi = pd.read_parquet(FUTOI_4H)
            futoi_t = futoi[futoi['ticker'] == ticker].copy()
            if len(futoi_t) > 0:
                futoi_t['date_only'] = pd.to_datetime(futoi_t['hour']).dt.date
                df_d1_futoi = futoi_t.groupby('date_only').agg({'fiz_buy_ratio': 'last', 'yur_buy_ratio': 'last'}).reset_index()
                df['date_only'] = df['dt_full'].dt.date
                df = pd.merge(df, df_d1_futoi, on='date_only', how='left')
                df = df.ffill()
        except Exception:
            pass

    # Заполняем fiz_buy_ratio=50, если нет
    if 'fiz_buy_ratio' not in df.columns:
        df['fiz_buy_ratio'] = 50

    return df


def main():
    sd = load_signals()
    print(f'signal_direction.json: {len(sd)} тикеров')
    print()

    tickers = []
    for f in sorted(DATA.glob('*_D1.parquet')):
        ticker = f.stem.replace('_D1', '')
        if (DATA / f'{ticker}_H4.parquet').exists() and (DATA / f'{ticker}_H1.parquet').exists():
            tickers.append(ticker)

    print(f'Тикеров для теста: {len(tickers)}')
    print()

    results = {'baseline': [], 'disb': [], 'disb_hi2': [], 'full': []}

    for ticker in tickers[:50]:
        try:
            df_d1 = load_candles_with_futoi(ticker, 'D1')
            df_4h = load_candles_with_futoi(ticker, 'H4')
            df_1h = load_candles_with_futoi(ticker, 'H1')
            if df_d1 is None or df_4h is None or df_1h is None:
                continue

            disb = get_disb(ticker)
            hi2 = get_hi2(ticker)
            ydir, ymed, ystd = get_yur(ticker, sd)

            # yur_buy_ratio из df_1h
            yur_val = None
            if 'yur_buy_ratio' in df_1h.columns and len(df_1h) > 0:
                yv = df_1h['yur_buy_ratio'].iloc[-1]
                yur_val = float(yv) if pd.notna(yv) else None

            # 4 версии (garch_vol=0)
            v_baseline = get_unified_scanner_verdict(df_d1, df_4h, df_1h, garch_vol=0)
            v_disb = get_unified_scanner_verdict(df_d1, df_4h, df_1h, garch_vol=0, disb=disb)
            v_disb_hi2 = get_unified_scanner_verdict(df_d1, df_4h, df_1h, garch_vol=0, disb=disb, hi2_value=hi2)
            v_full = get_unified_scanner_verdict(df_d1, df_4h, df_1h, garch_vol=0, disb=disb, hi2_value=hi2,
                                                  yur_buy_ratio=yur_val, yur_dir=ydir, yur_median=ymed, yur_std=ystd)

            if ticker == tickers[0]:
                print(f'  [ОТЛАДКА {ticker}] baseline: decision={v_baseline.get("decision")}, score={v_baseline.get("score")}')
                print(f'  [ОТЛАДКА {ticker}] full: decision={v_full.get("decision")}, score={v_full.get("score")}')
                f_b = v_full.get('factors', {})
                print(f'  [ОТЛАДКА {ticker}] full factors: yur_mod={f_b.get("yur_mod")}, disb_mod={f_b.get("disb_mod")}')

            results['baseline'].append((ticker, v_baseline.get('decision'), v_baseline.get('score')))
            results['disb'].append((ticker, v_disb.get('decision'), v_disb.get('score')))
            results['disb_hi2'].append((ticker, v_disb_hi2.get('decision'), v_disb_hi2.get('score')))
            results['full'].append((ticker, v_full.get('decision'), v_full.get('score')))
        except Exception as e:
            print(f'  ⚠️ {ticker}: {e}')

    print()
    print('=== РЕЗУЛЬТАТЫ ===')
    for name, res in results.items():
        if not res:
            print(f'  {name}: ПУСТОЙ')
            continue
        long_cnt = sum(1 for _, d, _ in res if d == 'LONG')
        short_cnt = sum(1 for _, d, _ in res if d == 'SHORT')
        wait_cnt = sum(1 for _, d, _ in res if d == 'WAIT')
        nodata_cnt = sum(1 for _, d, _ in res if d == 'NO_DATA')
        avg_score = sum(s or 0 for _, _, s in res) / len(res) if res else 0
        print(f'  {name}: LONG={long_cnt}, SHORT={short_cnt}, WAIT={wait_cnt}, NO_DATA={nodata_cnt}, avg_score={avg_score:.1f}')

    print()
    print('=== РАЗЛИЧИЯ (baseline vs full) ===')
    base_d = {t: d for t, d, _ in results['baseline']}
    full_d = {t: d for t, d, _ in results['full']}
    diff_cnt = 0
    for t in base_d:
        if base_d[t] != full_d.get(t):
            print(f'  {t}: baseline={base_d[t]} → full={full_d.get(t)}')
            diff_cnt += 1
    print(f'Всего различий: {diff_cnt} из {len(base_d)}')


if __name__ == '__main__':
    main()
