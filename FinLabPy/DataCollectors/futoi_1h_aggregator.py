"""
Сборщик FutOI 1H
Агрегирует 5-минутные данные FutOI в 1-часовые свечи.
Сохраняет в /root/finlab/data/futoi_1h/futoi_1h.parquet
"""

import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
import sys
sys.path.insert(0, '/root/finlab/FinLabPy')
from loguru import logger

# Настройка логов
LOG_DIR = Path("/root/finlab/logs")
LOG_DIR.mkdir(exist_ok=True)
log_file = LOG_DIR / f"{datetime.now().strftime('%Y-%m-%d')}_futoi_1h.log"
logger.add(log_file, rotation="1 day", retention="30 days")

# Пути
DATA_IN = Path("/root/finlab/data/futoi")
DATA_OUT = Path("/root/finlab/data/futoi_1h")
DATA_OUT.mkdir(exist_ok=True)
OUTPUT_FILE = DATA_OUT / "futoi_1h.parquet"

TICKERS = ["CNYRUBF", "GAZPF", "GLDRUBF", "IMOEXF", "SBERF"]


def load_raw_futoi():
    """Загружает все 5-минутные данные FutOI по всем тикерам."""
    dfs = []
    for ticker in TICKERS:
        f = DATA_IN / f"{ticker}_futoi.parquet"
        if not f.exists():
            logger.warning(f"Файл не найден: {f}")
            continue
        df = pd.read_parquet(f)
        dfs.append(df)
        logger.info(f"  {ticker}: {len(df)} записей")
    
    if not dfs:
        return None
    
    df_all = pd.concat(dfs, ignore_index=True)
    df_all['datetime'] = pd.to_datetime(
        df_all['tradedate'].astype(str) + ' ' + df_all['tradetime'].astype(str)
    )
    return df_all


def aggregate_to_1h(df):
    """Агрегирует 5-минутные данные до 1 часа.
    Берёт последнюю запись за каждый час (позиции на конец часа).
    """
    # Округляем до часа
    df['hour'] = df['datetime'].dt.floor('1h')
    
    # Для каждого тикера и часа берём последнюю запись
    result = []
    for ticker in df['ticker'].unique():
        df_t = df[df['ticker'] == ticker].copy()
        
        # Физики
        fiz = df_t[df_t['clgroup'] == 'FIZ'].copy()
        fiz = fiz.sort_values('datetime').groupby('hour').last().reset_index()
        fiz = fiz[['hour', 'pos_long', 'pos_short']].rename(columns={
            'pos_long': 'fiz_long', 'pos_short': 'fiz_short'
        })
        
        # Юрики
        yur = df_t[df_t['clgroup'] == 'YUR'].copy()
        yur = yur.sort_values('datetime').groupby('hour').last().reset_index()
        yur = yur[['hour', 'pos_long', 'pos_short']].rename(columns={
            'pos_long': 'yur_long', 'pos_short': 'yur_short'
        })
        
        # Объединяем
        merged = fiz.merge(yur, on='hour', how='outer')
        merged['ticker'] = ticker
        
        # Считаем ratio
        merged['fiz_total'] = merged['fiz_long'] + merged['fiz_short']
        merged['yur_total'] = merged['yur_long'] + merged['yur_short']
        merged['fiz_buy_ratio'] = (merged['fiz_long'] / merged['fiz_total'] * 100).round(2)
        merged['yur_buy_ratio'] = (merged['yur_long'] / merged['yur_total'] * 100).round(2)
        
        # Дельта за 1 час (изменение ratio)
        merged['fiz_ratio_delta'] = merged['fiz_buy_ratio'].diff().round(2)
        merged['yur_ratio_delta'] = merged['yur_buy_ratio'].diff().round(2)
        
        result.append(merged)
    
    return pd.concat(result, ignore_index=True)


def save_data(df_new):
    """Дописывает новые данные в общий файл, избегая дубликатов."""
    if OUTPUT_FILE.exists():
        df_old = pd.read_parquet(OUTPUT_FILE)
        # Удаляем часы, которые уже есть в старом файле
        existing_hours = set(zip(df_old['ticker'], df_old['hour']))
        df_new = df_new[~df_new.apply(lambda r: (r['ticker'], r['hour']) in existing_hours, axis=1)]
        df_all = pd.concat([df_old, df_new], ignore_index=True)
    else:
        df_all = df_new
    
    df_all = df_all.sort_values(['hour', 'ticker']).reset_index(drop=True)
    df_all.to_parquet(OUTPUT_FILE, index=False)
    logger.info(f"Сохранено: {OUTPUT_FILE}, строк: {len(df_all)} (новых: {len(df_new)})")
    
    return len(df_new)


def main():
    logger.info("=== Запуск агрегации FutOI 1H ===")
    
    df_raw = load_raw_futoi()
    if df_raw is None:
        logger.error("Нет данных для агрегации")
        return
    
    df_1h = aggregate_to_1h(df_raw)
    new_rows = save_data(df_1h)
    
    logger.info(f"Готово. Новых строк: {new_rows}")


if __name__ == "__main__":
    main()