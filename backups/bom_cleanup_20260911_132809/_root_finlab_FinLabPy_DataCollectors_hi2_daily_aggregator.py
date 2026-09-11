"""
Агрегатор дневных HI2 данных. Группирует внутридневные записи в одну строку на день.
Запускается после сборщика HI2.

Использование:
    python FinLabPy/DataCollectors/hi2_daily_aggregator.py
"""
import os
import sys
from pathlib import Path
from datetime import date

project_root = Path(__file__).parent.parent.parent if '__file__' in globals() else Path('.').absolute()
sys.path.insert(0, str(project_root))

import polars as pl
from FinLabPy.Utils import setup_logger

logger = setup_logger('hi2_aggregator')

DATA_DIR = project_root / 'data' / 'hi2'
OUTPUT_FILE = project_root / 'data' / 'hi2_daily.parquet'


def aggregate_all():
    """Агрегировать все файлы HI2 в дневной отчёт."""
    logger.info('Агрегация дневных HI2...')
    
    if not DATA_DIR.exists():
        logger.error('Папка с данными не найдена')
        return
    
    all_rows = []
    
    for f in sorted(DATA_DIR.glob('*_hi2.parquet')):
        ticker = f.stem.replace('_hi2', '')
        df = pl.read_parquet(f)
        
        if df.is_empty():
            continue
        
        # Группируем по дате
        daily = df.group_by(['ticker', 'engine', 'tradedate']).agg([
            pl.col('value').filter(pl.col('metric') == 'hhi_agressive').last().alias('hhi_agressive'),
            pl.col('value').filter(pl.col('metric') == 'hhi_volume').last().alias('hhi_volume'),
        ])
        
        all_rows.append(daily)
        logger.info(f'  {ticker}: {len(daily)} дней')
    
    if not all_rows:
        logger.warning('Нет данных для агрегации')
        return
    
    df_all = pl.concat(all_rows).sort(['ticker', 'tradedate'])
    df_all.write_parquet(OUTPUT_FILE)
    
    logger.info(f'Сохранено: {OUTPUT_FILE}')
    logger.info(f'  Всего строк: {len(df_all)}')
    logger.info(f'  Тикеров: {df_all["ticker"].n_unique()}')


if __name__ == '__main__':
    aggregate_all()
