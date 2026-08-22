"""Сборщик Mega Alerts (торговые аномалии) через AlgoPack API."""
import os
import sys
from pathlib import Path
from datetime import datetime, date, timedelta
import json

project_root = Path(__file__).parent.parent.parent if '__file__' in dir() else Path('.').absolute()
sys.path.insert(0, str(project_root))

import polars as pl
import requests
from MOEXPy.MOEXPy import MOEXPy
from FinLabPy.Utils import setup_logger

logger = setup_logger('mega_alert_collector')


class MegaAlertCollector:
    """Сборщик Mega Alerts для списка тикеров."""
    
    def __init__(self, api, data_dir: Path = None):
        self.api = api
        self.data_dir = data_dir or project_root / 'data' / 'mega_alerts'
        self.data_dir.mkdir(parents=True, exist_ok=True)
    
    @staticmethod
    def _resolve_full_code(short_code):
        """Получить полный код фьючерса (ближайший активный контракт)."""
        cache_file = Path(__file__).parent / "contract_cache.json"
        cache = {}
        if cache_file.exists():
            with open(cache_file) as f:
                cache = json.load(f)
        
        today = datetime.now().strftime("%Y-%m-%d")
        if short_code in cache and cache[short_code].get("date") == today:
            return cache[short_code]["code"]
        
        try:
            url = "https://iss.moex.com/iss/engines/futures/markets/forts/securities.json"
            r = requests.get(url, timeout=10)
            data = r.json()["securities"]
            cols = data["columns"]
            rows = data["data"]
            secid_idx = cols.index("SECID")
            sectype_idx = cols.index("SECTYPE")
            date_idx = cols.index("LASTTRADEDATE")
            active = []
            for row in rows:
                if row[sectype_idx].upper() == short_code.upper() and row[date_idx] > today:
                    active.append((row[date_idx], row[secid_idx]))
            if active:
                active.sort()
                full_code = active[0][1]
                cache[short_code] = {"code": full_code, "date": today}
                with open(cache_file, "w") as f:
                    json.dump(cache, f)
                return full_code
        except:
            pass
        return short_code

    def collect_all(self):
        """Собрать Mega Alerts для всех тикеров."""
        logger.info(f'Начало сбора Mega Alerts за {date.today()}')
        
        # Тикеры из конфига
        cfg_path = Path(__file__).parent / 'tickers_config.json'
        if cfg_path.exists():
            with open(cfg_path) as f:
                cfg = json.load(f)
            tickers = cfg.get('stocks', []) + cfg.get('futures', [])
        else:
            tickers = ['SBER', 'GAZP', 'LKOH', 'ROSN']
        
        total_alerts = 0
        
        for ticker in tickers:
            try:
                alerts = self._collect_one(ticker)
                total_alerts += len(alerts)
                logger.info(f'  {ticker}: {len(alerts)} алертов')
            except Exception as e:
                logger.error(f'  {ticker}: ОШИБКА — {e}')
        
        logger.info(f'Готово! Всего алертов: {total_alerts}')
    
    def _collect_one(self, ticker: str) -> list:
        """Собрать Mega Alerts для одного тикера."""
        # Определяем engine и полный код контракта
        cfg_path = Path(__file__).parent / 'tickers_config.json'
        engine = 'stocks'
        api_ticker = ticker
        
        if cfg_path.exists():
            with open(cfg_path) as f:
                cfg = json.load(f)
            if ticker in cfg.get('futures', []):
                engine = 'futures'
                # Для срочных фьючерсов нужен полный код (RIU6, BRU6 и т.д.)
                api_ticker = self._resolve_full_code(ticker)
        
        # Получаем алерты за последние 7 дней
        end_date = date.today()
        start_date = end_date - timedelta(days=7)
        
        raw = self.api.get_alerts(engine, api_ticker, date=end_date)
        
        if not raw or 'data' not in raw or 'data' not in raw['data']:
            return []
        
        alerts_data = raw['data']
        columns = alerts_data.get('columns', [])
        data = alerts_data.get('data', [])
        
        if not data:
            return []
        
        # Сохраняем
        file_path = self.data_dir / f'{ticker}_alerts.parquet'
        rows = [dict(zip(columns, row)) for row in data]
        df = pl.DataFrame(rows)
        
        if file_path.exists():
            df_existing = pl.read_parquet(file_path)
            df_combined = pl.concat([df_existing, df])
        else:
            df_combined = df
        
        # Приводим threshold к Float64 (может быть Int64 в старых файлах)
        if 'threshold' in df_combined.columns:
            df_combined = df_combined.with_columns(pl.col('threshold').cast(pl.Float64))
        
        df_combined.write_parquet(file_path)
        return rows


if __name__ == '__main__':
    api = MOEXPy(token=os.getenv('MOEX_TOKEN'))
    collector = MegaAlertCollector(api)
    collector.collect_all()
