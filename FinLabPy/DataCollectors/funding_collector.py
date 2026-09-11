"""
Сборщик ставок фандинга (SWAPRATE) вечных фьючерсов через MOEX ISS API.
Запускается раз в день через cron, накапливает историю в parquet.

Использование:
    python FinLabPy/DataCollectors/funding_collector.py
"""
import os
import sys
from pathlib import Path
from datetime import date

project_root = Path(__file__).parent.parent.parent if '__file__' in dir() else Path('.').absolute()
sys.path.insert(0, str(project_root))

import polars as pl
import requests
from FinLabPy.Utils import setup_logger

logger = setup_logger('funding_collector')


class FundingCollector:
    """Сборщик ставок фандинга для вечных фьючерсов."""

    # Тикеры вечных фьючерсов
    TICKERS = ['USDRUBF', 'EURRUBF', 'CNYRUBF', 'IMOEXF', 'SBERF', 'GAZPF', 'GLDRUBF']

    def __init__(self, data_dir: Path = None):
        self.data_dir = data_dir or project_root / 'data' / 'funding'
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def collect_all(self):
        """Собрать фандинг для всех тикеров."""
        today = date.today()
        logger.info(f'Начало сбора фандинга за {today}')

        # Запрашиваем все тикеры одним запросом
        url = 'https://iss.moex.com/iss/engines/futures/markets/forts/securities.json'
        params = {
            'securities': ','.join(self.TICKERS),
            'iss.meta': 'off',
            'iss.only': 'marketdata',
            'marketdata.columns': 'SECID,SWAPRATE,LAST'
        }

        try:
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error(f'Ошибка запроса: {e}')
            return

        marketdata = data.get('marketdata', {})
        cols = marketdata.get('columns', [])
        rows = marketdata.get('data', [])

        if not rows:
            logger.warning('Нет данных в ответе')
            return

        # Парсим
        records = []
        for row in rows:
            d = dict(zip(cols, row))
            records.append({
                'ticker': d['SECID'],
                'date': str(today),
                'swaprate': float(d.get('SWAPRATE', 0)),
                'last_price': float(d.get('LAST', 0)),
            })

        df_new = pl.DataFrame(records)
        logger.info(f'Получено записей: {len(df_new)}')

        # Сохраняем
        file_path = self.data_dir / 'funding.parquet'

        if file_path.exists():
            df_existing = pl.read_parquet(file_path)
            # Удаляем старые записи за сегодня
            df_existing = df_existing.filter(pl.col('date') != str(today))
            df_combined = pl.concat([df_existing, df_new])
        else:
            df_combined = df_new

        df_combined.write_parquet(file_path)

        for row in records:
            logger.info(f"  {row['ticker']}: swaprate={row['swaprate']:.4f}%, last={row['last_price']}")

        logger.info(f'Сохранено строк: {len(df_combined)} всего, {len(df_new)} новых')


if __name__ == '__main__':
    collector = FundingCollector()
    collector.collect_all()
