"""
Агрегатор Super Candles в 4-часовые свечи (H4).
Группирует 5-минутные свечи в 4-часовые блоки: 07:00-11:00, 11:00-15:00, 15:00-19:00.
Запускается после ежедневного сбора Super Candles.

Использование:
    python FinLabPy/DataCollectors/supercandles_h4_aggregator.py
"""
import sys
from pathlib import Path
from datetime import date, timedelta

project_root = Path(__file__).parent.parent.parent if '__file__' in globals() else Path('.').absolute()
sys.path.insert(0, str(project_root))

import polars as pl
from FinLabPy.Utils import setup_logger

logger = setup_logger('supercandles_h4')

DATA_DIR = project_root / 'data' / 'supercandles'
OUTPUT_DIR = project_root / 'data' / 'supercandles_h4'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Определяем 4-часовые блоки (МСК)
H4_BLOCKS = [
    ('07:00:00', '11:00:00', '07:00'),
    ('11:00:00', '15:00:00', '11:00'),
    ('15:00:00', '19:00:00', '15:00'),
]


def aggregate_all():
    """Агрегировать все файлы Super Candles в H4."""
    logger.info('Агрегация Super Candles в H4...')

    if not DATA_DIR.exists():
        logger.error('Папка с данными не найдена')
        return

    today = str(date.today())
    lookback_dates = [(date.today() - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(3)]
    all_h4_rows = []

    for f in sorted(DATA_DIR.glob('*_supercandles.parquet')):
        ticker = f.stem.replace('_supercandles', '')
        df = pl.read_parquet(f)

        if df.is_empty():
            continue

        # Фильтруем только сегодняшние данные
        df_today = df.filter(pl.col('tradedate').is_in(lookback_dates))

        if df_today.is_empty():
            continue

        # Преобразуем tradetime во время
        df_today = df_today.with_columns(
            pl.col('tradetime').str.to_time('%H:%M:%S')
        )

        for block_start, block_end, label in H4_BLOCKS:
            start_time = pl.time(hour=int(block_start[:2]), minute=int(block_start[3:5]))
            end_time = pl.time(hour=int(block_end[:2]), minute=int(block_end[3:5]))

            block_df = df_today.filter(
                (pl.col('tradetime') >= start_time) & (pl.col('tradetime') < end_time)
            )

            if block_df.is_empty():
                continue

            # Агрегируем в OHLCV + специфичные метрики
            h4_row = {
                'ticker': ticker,
                'tradedate': today,
                'block': label,
                'pr_open': block_df['pr_open'].first(),
                'pr_high': block_df['pr_high'].max(),
                'pr_low': block_df['pr_low'].min(),
                'pr_close': block_df['pr_close'].last(),
                'vol': block_df['vol'].sum(),
                'val': block_df['val'].sum(),
                'trades': block_df['trades'].sum(),
                'trades_b': block_df['trades_b'].sum(),
                'trades_s': block_df['trades_s'].sum(),
                'vol_b': block_df['vol_b'].sum(),
                'vol_s': block_df['vol_s'].sum(),
                'val_b': block_df['val_b'].sum(),
                'val_s': block_df['val_s'].sum(),
                'disb_avg': block_df['disb'].mean(),
            }
            all_h4_rows.append(h4_row)

        logger.info(f'  {ticker}: {len([r for r in all_h4_rows if r["ticker"] == ticker])} блоков')

    if not all_h4_rows:
        logger.warning('Нет данных для H4-агрегации')
        return

    df_h4 = pl.DataFrame(all_h4_rows).sort(['ticker', 'block'])

    # Сохраняем
    output_file = OUTPUT_DIR / f'supercandles_h4_{today}.parquet'
    df_h4.write_parquet(output_file)

    logger.info(f'Сохранено: {output_file}')
    logger.info(f'  Всего строк: {len(df_h4)}')
    logger.info(f'  Тикеров: {df_h4["ticker"].n_unique()}')


if __name__ == '__main__':
    aggregate_all()
