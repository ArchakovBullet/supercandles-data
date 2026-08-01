"""Агрегация FutOI 1H в 4H"""
import pandas as pd
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from Utils.Logger import setup_logger

logger = setup_logger('futoi_4h')

DATA_1H = Path('/root/finlab/data/futoi_1h/futoi_1h.parquet')
DATA_4H = Path('/root/finlab/data/futoi_4h/futoi_4h.parquet')
DATA_4H.parent.mkdir(exist_ok=True)

def aggregate():
    if not DATA_1H.exists():
        logger.warning("Нет данных 1H")
        return
    
    df = pd.read_parquet(DATA_1H)
    df['hour'] = pd.to_datetime(df['hour'])
    df['block'] = df['hour'].dt.floor('4h')
    df['hour'] = df['block']
    
    agg = df.groupby(['ticker', 'block']).agg({
        'fiz_long': 'last', 'fiz_short': 'last',
        'yur_long': 'last', 'yur_short': 'last',
        'fiz_total': 'last', 'yur_total': 'last',
        'fiz_buy_ratio': 'mean', 'yur_buy_ratio': 'mean',
        'fiz_ratio_delta': 'sum', 'yur_ratio_delta': 'sum'
    }).reset_index()
    
    # Добавляем колонку hour (совместимость с дашбордом)
    agg['hour'] = agg['block']
    
    agg.to_parquet(DATA_4H, index=False)
    logger.info(f"FutOI 4H: {len(agg)} строк, последняя: {agg['block'].max()}")

if __name__ == '__main__':
    aggregate()
