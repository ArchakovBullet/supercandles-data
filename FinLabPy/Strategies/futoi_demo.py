"""
FutOI Демо-стратегия с относительным порогом.
"""
import os, sys
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).parent.parent.parent if '__file__' in dir() else Path('.').absolute()
sys.path.insert(0, str(project_root))

import polars as pl
from MOEXPy.MOEXPy import MOEXPy
from FinLabPy.Utils import setup_logger

logger = setup_logger('futoi_demo')


def run_demo():
    api = MOEXPy(token=os.getenv('MOEX_TOKEN'))
    
    futoi_path = project_root / 'data' / 'futoi_daily.parquet'
    if not futoi_path.exists():
        logger.error(f'Нет данных: {futoi_path}')
        return
    
    df = pl.read_parquet(futoi_path)
    
    tickers = ['GLDRUBF', 'CNYRUBF', 'SBERF', 'GAZPF', 'IMOEXF']
    thresholds_rel = {
        'GLDRUBF': 0.05,
        'CNYRUBF': 0.15,
        'SBERF': 0.20,
        'GAZPF': 0.20,
        'IMOEXF': 0.10,
    }
    
    logger.info(f'{"="*60}')
    logger.info(f'FutOI ДЕМО — {datetime.now().strftime("%Y-%m-%d %H:%M")}')
    logger.info(f'{"="*60}')
    logger.info(f'Данные: {df["tradedate"].min()} — {df["tradedate"].max()}')
    logger.info(f'Записей: {len(df)}')
    
    for ticker in tickers:
        td = df.filter(pl.col('ticker') == ticker).sort('tradedate', descending=True)
        
        if len(td) < 2:
            continue
        
        latest = td.row(0, named=True)
        
        phys_net = float(latest.get('phys_net') or 0)
        phys_change = float(latest.get('phys_change') or 0)
        pct = abs(phys_change) / max(abs(phys_net), 1) * 100 if phys_net != 0 else 0
        
        tr = thresholds_rel[ticker]
        ta = abs(phys_net) * tr
        
        if phys_change > ta:
            sig = 'BUY '
        elif phys_change < -ta:
            sig = 'SELL'
        else:
            sig = 'HOLD'
        
        emoji = '🟢' if sig == 'BUY ' else '🔴' if sig == 'SELL' else '⚪'
        logger.info(f'{emoji} {sig} {ticker:<8} | change={phys_change:>+13,.0f} ({pct:>5.1f}%) | net={phys_net:>+13,.0f} | порог={ta:>10,.0f} ({tr:.0%}) | {latest["tradedate"]}')


if __name__ == '__main__':
    run_demo()
