"""
Агрегирует внутридневные FutOI в дневные нетто-позиции
Запускается после сборщика
"""
import sys
from pathlib import Path
import polars as pl

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from FinLabPy.Utils import setup_logger

logger = setup_logger('futoi_aggregator')

DATA_DIR = project_root / 'data' / 'futoi'
DAILY_FILE = project_root / 'data' / 'futoi_daily.parquet'

TICKERS = ['GLDRUBF', 'SBERF', 'GAZPF', 'IMOEXF', 'CNYRUBF']


def aggregate_daily(ticker: str) -> pl.DataFrame:
    """Взять последние позиции за каждый день"""
    filepath = DATA_DIR / f"{ticker}_futoi.parquet"

    if not filepath.exists():
        logger.warning(f"Нет файла: {filepath}")
        return pl.DataFrame()

    df = pl.read_parquet(filepath)

    daily = (
        df
        .sort('sess_id')
        .group_by(['ticker', 'tradedate', 'clgroup'])
        .agg([
            pl.col('pos_long').last().alias('pos_long_total'),
            pl.col('pos_short').last().alias('pos_short_total'),
            pl.col('pos').last().alias('pos_net'),
        ])
    )

    fiz = daily.filter(pl.col('clgroup') == 'FIZ').select([
        'ticker', 'tradedate',
        pl.col('pos_long_total').alias('phys_long'),
        pl.col('pos_short_total').alias('phys_short'),
        pl.col('pos_net').alias('phys_net'),
    ])

    yur = daily.filter(pl.col('clgroup') == 'YUR').select([
        'ticker', 'tradedate',
        pl.col('pos_long_total').alias('jur_long'),
        pl.col('pos_short_total').alias('jur_short'),
        pl.col('pos_net').alias('jur_net'),
    ])

    result = fiz.join(yur, on=['ticker', 'tradedate'], how='full')

    result = result.with_columns([
        (pl.col('phys_net') - pl.col('phys_net').shift(1)).alias('phys_change'),
    ])

    return result.sort(['ticker', 'tradedate'])


def fmt_val(v):
    """Безопасное форматирование (None -> '·')"""
    if v is None:
        return '·'
    return f'{v:+.0f}'


def main():
    logger.info("Агрегация дневных FutOI...")

    all_daily = []

    for ticker in TICKERS:
        daily = aggregate_daily(ticker)
        if not daily.is_empty():
            all_daily.append(daily)
            logger.info(f"{ticker}: {len(daily)} дней")

    if all_daily:
        combined = pl.concat(all_daily)
        combined.write_parquet(DAILY_FILE)
        logger.info(f"Сохранено: {DAILY_FILE}")
        logger.info(f"  Всего строк: {len(combined)}")
        if len(combined) > 0:
            logger.info(f"  Диапазон дат: {combined['tradedate'].min()} - {combined['tradedate'].max()}")

        gld = combined.filter(pl.col('ticker') == 'GLDRUBF')
        if not gld.is_empty():
            logger.info(f"\nGLDRUBF последние дни:")
            for row in gld.iter_rows(named=True):
                logger.info(
                    f"  {row['tradedate']}: "
                    f"phys_net={fmt_val(row['phys_net'])}, "
                    f"phys_change={fmt_val(row['phys_change'])}, "
                    f"jur_net={fmt_val(row['jur_net'])}"
                )
    else:
        logger.warning("Нет данных для агрегации!")


if __name__ == '__main__':
    main()
