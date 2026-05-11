# -*- coding: utf-8 -*-
"""
Агрегатор Super Candles: 5-минутки → дневные данные
"""
import sys
from pathlib import Path
import polars as pl

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from FinLabPy.Utils import setup_logger

logger = setup_logger('supercandles_aggregator')

DATA_DIR = project_root / 'data' / 'supercandles'
DAILY_FILE = project_root / 'data' / 'supercandles_daily.parquet'

TICKERS = ['SBER', 'LKOH', 'ROSN', 'VTBR', 'TATN', 'HYDR', 'IRAO', 'GMKN', 'PLZL']


def aggregate_daily(ticker: str) -> pl.DataFrame:
    """Агрегировать 5-минутки в дневные свечи"""
    filepath = DATA_DIR / f"{ticker}_supercandles.parquet"

    if not filepath.exists():
        logger.warning(f"Нет файла: {filepath}")
        return pl.DataFrame()

    df = pl.read_parquet(filepath)

    daily = df.group_by(['secid', 'tradedate']).agg([
        # Стандартные OHLCV
        pl.col('pr_open').first().alias('open'),
        pl.col('pr_high').max().alias('high'),
        pl.col('pr_low').min().alias('low'),
        pl.col('pr_close').last().alias('close'),
        pl.col('vol').sum().alias('volume'),
        pl.col('val').sum().alias('value'),
        pl.col('trades').sum().alias('trades'),

        # Покупки
        pl.col('trades_b').sum().alias('trades_buy'),
        pl.col('vol_b').sum().alias('vol_buy'),
        pl.col('val_b').sum().alias('val_buy'),

        # Продажи
        pl.col('trades_s').sum().alias('trades_sell'),
        pl.col('vol_s').sum().alias('vol_sell'),
        pl.col('val_s').sum().alias('val_sell'),

        # VWAP покупок/продаж (средневзвешенная по объёму)
        (pl.col('pr_vwap_b') * pl.col('vol_b')).sum().alias('vwap_b_sum'),
        (pl.col('pr_vwap_s') * pl.col('vol_s')).sum().alias('vwap_s_sum'),

        # Дисбаланс (средний по объёму)
        (pl.col('disb') * pl.col('vol')).sum().alias('disb_weighted'),
        pl.col('vol').sum().alias('vol_total_for_disb'),
    ])

    # Вычисляем производные
    daily = daily.with_columns([
        # VWAP
        (pl.col('vwap_b_sum') / pl.col('vol_buy')).alias('vwap_buy'),
        (pl.col('vwap_s_sum') / pl.col('vol_sell')).alias('vwap_sell'),

        # Средневзвешенный дисбаланс
        (pl.col('disb_weighted') / pl.col('vol_total_for_disb')).alias('disb'),

        # Buy ratio (доля покупок в объёме)
        (pl.col('vol_buy') / (pl.col('vol_buy') + pl.col('vol_sell'))).alias('buy_ratio'),

        # Нетто-объём (покупки - продажи)
        (pl.col('vol_buy') - pl.col('vol_sell')).alias('net_vol'),
    ])

    # Убираем вспомогательные колонки
    daily = daily.drop(['vwap_b_sum', 'vwap_s_sum', 'disb_weighted', 'vol_total_for_disb'])

    return daily.sort(['secid', 'tradedate'])


def main():
    logger.info("Агрегация дневных Super Candles...")

    all_daily = []

    for ticker in TICKERS:
        daily = aggregate_daily(ticker)
        if not daily.is_empty():
            all_daily.append(daily)
            logger.info(f"{ticker}: {len(daily)} дней")

    if all_daily:
        combined = pl.concat(all_daily)
        combined.write_parquet(DAILY_FILE)
        logger.info(f"\nСохранено: {DAILY_FILE}")
        logger.info(f"  Всего строк: {len(combined)}")
        logger.info(f"  Тикеров: {combined['secid'].n_unique()}")

        # Покажем SBER
        sber = combined.filter(pl.col('secid') == 'SBER')
        if not sber.is_empty():
            logger.info(f"\nSBER — последние 3 дня:")
            for row in sber.tail(3).iter_rows(named=True):
                logger.info(
                    f"  {row['tradedate']}: "
                    f"close={row['close']:.1f}, "
                    f"buy_ratio={row['buy_ratio']:.2f}, "
                    f"disb={row['disb']:.2f}"
                )
    else:
        logger.warning("Нет данных для агрегации!")


if __name__ == '__main__':
    main()
