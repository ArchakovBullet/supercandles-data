"""
Ежедневный сборщик данных FutOI (открытые позиции физ/юр лиц)
Сохраняет в Parquet для компактности и скорости
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

logger = setup_logger('futoi_collector')

# Только реально торгуемые фьючерсы MOEX (VTBRF и LKOHF не торгуются)
def _load_tickers():
    import json
    cfg_path = Path(__file__).parent / 'tickers_config.json'
    if cfg_path.exists():
        with open(cfg_path) as f:
            cfg = json.load(f)
        return cfg.get('futures', ['GLDRUBF', 'SBERF', 'GAZPF', 'IMOEXF', 'CNYRUBF'])
    return ['GLDRUBF', 'SBERF', 'GAZPF', 'IMOEXF', 'CNYRUBF']

TICKERS = _load_tickers()
DATA_DIR = project_root / 'data' / 'futoi'
LOOKBACK_DAYS = 5


def _resolve_full_code(short_code):
    import json, requests
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


def collect_futoi(ticker: str, api: MOEXPy) -> pl.DataFrame:
    """Собрать данные FutOI за LOOKBACK_DAYS"""
    dt_till = datetime.now()
    dt_from = dt_till - timedelta(days=LOOKBACK_DAYS)

    try:
        raw_data = api.get_futoi(ticker, dt_from, dt_till)

        data_rows = raw_data.get('futoi', {}).get('data', [])
        columns = raw_data.get('futoi', {}).get('columns', [])

        if not data_rows:
            logger.warning(f"{ticker}: нет данных")
            return pl.DataFrame()

        col_idx = {name: i for i, name in enumerate(columns)}

        rows = []
        for row in data_rows:
            pos_short_val = row[col_idx['pos_short']]
            rows.append({
                'sess_id': row[col_idx['sess_id']],
                'seqnum': row[col_idx['seqnum']],
                'tradedate': str(row[col_idx['tradedate']])[:10],
                'tradetime': str(row[col_idx['tradetime']]),
                'ticker': row[col_idx['ticker']],
                'clgroup': row[col_idx['clgroup']],
                'pos': int(row[col_idx['pos']]),
                'pos_long': int(row[col_idx['pos_long']]),
                'pos_short': abs(int(pos_short_val)) if pos_short_val else 0,
                'pos_long_num': int(row[col_idx['pos_long_num']]),
                'pos_short_num': int(row[col_idx['pos_short_num']]),
            })

        df = pl.DataFrame(rows)
        logger.info(f"{ticker}: загружено {len(df)} записей")
        return df

    except Exception as e:
        logger.error(f"{ticker}: ошибка - {e}")
        return pl.DataFrame()


def merge_with_existing(new_df: pl.DataFrame, filepath: Path) -> pl.DataFrame:
    """Объединить новые данные с существующими, удалить дубли"""
    if not filepath.exists():
        return new_df

    existing = pl.read_parquet(filepath)

    key_cols = ['ticker', 'tradedate', 'tradetime', 'clgroup']
    existing_keys = existing.select(key_cols)
    new_unique = new_df.join(existing_keys, on=key_cols, how='anti')

    merged = pl.concat([existing, new_unique])
    logger.info(f"  Было: {len(existing)}, Новых: {len(new_unique)}, Стало: {len(merged)}")
    return merged


def main():
    logger.info("=" * 60)
    logger.info("ЗАПУСК СБОРЩИКА FutOI")
    logger.info(f"Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    token = os.getenv('MOEX_TOKEN')
    api = MOEXPy(token=token)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    total_new = 0

    for ticker in TICKERS:
        logger.info(f"\n--- {ticker} ---")
        new_df = collect_futoi(ticker, api)

        if new_df.is_empty():
            continue

        filepath = DATA_DIR / f"{ticker}_futoi.parquet"
        merged = merge_with_existing(new_df, filepath)
        merged.write_parquet(filepath)

        total_new += len(new_df)

    logger.info(f"\nГотово! Всего новых записей: {total_new}")
    logger.info(f"Данные в: {DATA_DIR}")


if __name__ == '__main__':
    main()
