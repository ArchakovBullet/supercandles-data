"""
Сборщик TRIN (Индекс Армса) — ежедневное сохранение в parquet.
Запускается по cron раз в сутки.
"""

import pandas as pd
from pathlib import Path
from datetime import datetime
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from My_Indicators.arms_index import calculate_trin
from Utils.Logger import setup_logger

logger = setup_logger('trin_collector')

DATA_DIR = Path('/root/finlab/data')
OUTPUT_FILE = DATA_DIR / 'sector_indices' / 'TRIN_history.parquet'
OUTPUT_FILE.parent.mkdir(exist_ok=True)

def collect_trin():
    logger.info("Сбор TRIN...")
    
    result = calculate_trin(data_dir=DATA_DIR / 'candles')
    
    if result['trin'] == 0:
        logger.warning("TRIN = 0, данные не собраны")
        return
    
    row = {
        'date': datetime.now().strftime('%Y-%m-%d'),
        'trin': result['trin'],
        'advancing': result['advancing'],
        'declining': result['declining'],
        'adv_volume': result['adv_volume'],
        'dec_volume': result['dec_volume'],
        'signal': result['signal'],
        'level': result['level'],
    }
    
    df_new = pd.DataFrame([row])
    
    if OUTPUT_FILE.exists():
        df_old = pd.read_parquet(OUTPUT_FILE)
        df_old = df_old[df_old['date'] != row['date']]
        df_all = pd.concat([df_old, df_new], ignore_index=True)
    else:
        df_all = df_new
    
    df_all.to_parquet(OUTPUT_FILE, index=False)
    logger.info(f"TRIN={result['trin']} сохранён. Всего записей: {len(df_all)}")

if __name__ == '__main__':
    collect_trin()
