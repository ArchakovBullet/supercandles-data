"""
Сборщик истории HI2 (индекс концентрации Херфиндаля-Хиршмана) через MOEX API.
Запускается раз в день через cron, накапливает историю в parquet.

Использование:
    python FinLabPy/DataCollectors/hi2_collector.py
"""
import os
import sys
from pathlib import Path
from datetime import datetime, date

project_root = Path(__file__).parent.parent.parent if '__file__' in dir() else Path('.').absolute()
sys.path.insert(0, str(project_root))

import polars as pl
from MOEXPy.MOEXPy import MOEXPy
from FinLabPy.Utils import setup_logger

logger = setup_logger('hi2_collector')


class HI2Collector:
    """Сборщик HI2 для списка тикеров."""
    
    TICKERS = {
        'AFLT': 'stocks', 'SBER': 'stocks', 'GAZP': 'stocks', 'GMKN': 'stocks', 'YNDX': 'stocks', 'LKOH': 'stocks', 'HYDR': 'stocks', 'IRAO': 'stocks', 'PLZL': 'stocks', 'ROSN': 'stocks', 'TATN': 'stocks', 'VTBR': 'stocks', 'AFKS': 'stocks', 'T': 'stocks',
        'GLDRUBF': 'futures', 'CNYRUBF': 'futures', 'SBERF': 'futures', 'GAZPF': 'futures', 'IMOEXF': 'futures',
    }
    
    def __init__(self, api, data_dir: Path = None):
        self.api = api
        self.data_dir = data_dir or project_root / 'data' / 'hi2'
        self.data_dir.mkdir(parents=True, exist_ok=True)
    
    def collect_all(self):
        """Собрать HI2 для всех тикеров."""
        logger.info(f'Начало сбора HI2 за {date.today()}')
        total_new = 0
        
        for ticker, engine in self.TICKERS.items():
            try:
                new_rows = self._collect_one(ticker, engine)
                total_new += new_rows
                logger.info(f'  {ticker}: {new_rows} новых записей')
            except Exception as e:
                logger.error(f'  {ticker}: ОШИБКА — {e}')
        
        logger.info(f'Готово! Всего новых записей: {total_new}')
    
    def _collect_one(self, ticker: str, engine: str) -> int:
        """Собрать HI2 для одного тикера."""
        raw = self.api.get_hi2(engine, ticker, date.today())
        
        if not raw or 'data' not in raw or 'data' not in raw['data']:
            return 0
        
        hi2_data = raw['data']
        columns = hi2_data.get('columns', [])
        data = hi2_data.get('data', [])
        
        if not data:
            return 0
        
        # Парсим — берём ту дату, которую вернул API
        rows = []
        for row in data:
            row_dict = dict(zip(columns, row))
            trade_date = str(row_dict.get('tradedate', ''))[:10]
            rows.append({
                'ticker': ticker,
                'engine': engine,
                'tradedate': trade_date,
                'tradetime': row_dict.get('tradetime', ''),
                'metric': row_dict.get('metric', ''),
                'value': int(row_dict.get('value', 0)),
                'systime': row_dict.get('SYSTIME', ''),
            })
        
        df_new = pl.DataFrame(rows)
        
        # Сохраняем
        file_path = self.data_dir / f'{ticker}_hi2.parquet'
        
        if file_path.exists():
            df_existing = pl.read_parquet(file_path)
            # Удаляем старые записи за те же даты
            new_dates = df_new['tradedate'].unique()
            df_existing = df_existing.filter(~pl.col('tradedate').is_in(new_dates))
            df_combined = pl.concat([df_existing, df_new])
        else:
            df_combined = df_new
        
        df_combined.write_parquet(file_path)
        return len(df_new)


if __name__ == '__main__':
    api = MOEXPy(token=os.getenv('MOEX_TOKEN'))
    collector = HI2Collector(api)
    collector.collect_all()
