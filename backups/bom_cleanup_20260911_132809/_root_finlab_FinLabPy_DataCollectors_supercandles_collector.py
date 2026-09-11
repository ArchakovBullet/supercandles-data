# -*- coding: utf-8 -*-
"""
Сборщик данных Super Candles (tradestats) через Algopack API
Аналогичен сборщикам FutOI и HI2
"""
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
import polars as pl

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from MOEXPy.MOEXPy import MOEXPy
from FinLabPy.Utils import setup_logger

logger = setup_logger('supercandles_collector')

# 10 ликвидных акций из разных секторов
def _load_tickers():
    import json
    cfg_path = Path(__file__).parent / 'tickers_config.json'
    if cfg_path.exists():
        with open(cfg_path) as f:
            cfg = json.load(f)
        return cfg.get('stocks', ['SBER', 'LKOH', 'ROSN', 'VTBR', 'TATN', 'HYDR', 'IRAO', 'GMKN', 'PLZL', 'YDEX'])
    return ['SBER', 'LKOH', 'ROSN', 'VTBR', 'TATN', 'HYDR', 'IRAO', 'GMKN', 'PLZL', 'YDEX']

TICKERS = _load_tickers()
DATA_DIR = project_root / 'data' / 'supercandles'
LOOKBACK_DAYS = 5  # собираем последние 5 дней

# Колонки tradestats (из образца)
COLUMNS = [
    'tradedate', 'tradetime', 'secid',
    'pr_open', 'pr_high', 'pr_low', 'pr_close', 'pr_std',
    'vol', 'val', 'trades', 'pr_vwap', 'pr_change',
    'trades_b', 'trades_s', 'val_b', 'val_s', 'vol_b', 'vol_s',
    'disb', 'pr_vwap_b', 'pr_vwap_s', 'SYSTIME',
    'sec_pr_open', 'sec_pr_high', 'sec_pr_low', 'sec_pr_close'
]


def collect_tradestats(ticker: str, api: MOEXPy) -> pl.DataFrame:
    """Собрать tradestats для одного тикера"""
    dt_till = datetime.now()
    dt_from = dt_till - timedelta(days=LOOKBACK_DAYS)

    try:
        raw_data = api.get_tradestats(ticker, dt_from, dt_till)

        data_rows = raw_data.get('data', {}).get('data', [])
        if not data_rows:
            logger.warning(f"{ticker}: нет данных")
            return pl.DataFrame()

        rows = []
        for row in data_rows:
            d = {}
            for i, col in enumerate(COLUMNS):
                val = row[i] if i < len(row) else None
                if col in ['tradedate', 'tradetime', 'secid', 'SYSTIME']:
                    d[col] = str(val) if val else ''
                elif col in ['trades', 'trades_b', 'trades_s', 'vol', 'vol_b', 'vol_s']:
                    try:
                        d[col] = int(val) if val else 0
                    except (ValueError, TypeError):
                        d[col] = 0
                else:
                    try:
                        d[col] = float(val) if val else 0.0
                    except (ValueError, TypeError):
                        d[col] = 0.0
            rows.append(d)

        df = pl.DataFrame(rows)
        logger.info(f"{ticker}: загружено {len(df)} записей")
        return df

    except Exception as e:
        logger.error(f"{ticker}: ошибка - {e}")
        return pl.DataFrame()


def merge_with_existing(new_df: pl.DataFrame, filepath: Path) -> pl.DataFrame:
    """Объединить с существующими, удалить дубли"""
    if not filepath.exists():
        return new_df

    existing = pl.read_parquet(filepath)
    key_cols = ['secid', 'tradedate', 'tradetime']
    existing_keys = existing.select(key_cols)
    new_unique = new_df.join(existing_keys, on=key_cols, how='anti')
    merged = pl.concat([existing, new_unique])
    logger.info(f"  Было: {len(existing)}, Новых: {len(new_unique)}, Стало: {len(merged)}")
    return merged


def main():
    logger.info("=" * 60)
    logger.info("ЗАПУСК СБОРЩИКА Super Candles")
    logger.info(f"Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    token = os.getenv('MOEX_TOKEN')
    if not token:
        from dotenv import load_dotenv
        load_dotenv('/root/finlab/.env')
        token = os.getenv('MOEX_TOKEN')
    api = MOEXPy(token=token)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    total_new = 0

    for ticker in TICKERS:
        logger.info(f"\n--- {ticker} ---")
        new_df = collect_tradestats(ticker, api)

        if new_df.is_empty():
            continue

        filepath = DATA_DIR / f"{ticker}_supercandles.parquet"
        merged = merge_with_existing(new_df, filepath)
        merged.write_parquet(filepath)

        total_new += len(new_df)

    logger.info(f"\nГотово! Всего новых записей: {total_new}")
    logger.info(f"Данные в: {DATA_DIR}")


if __name__ == '__main__':
    main()
