"""
Портфельная стратегия на основе FutOI для сервера (исправленная).
Сигнал: изменение позиций физиков (phys_change) > порога.
"""
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta

project_root = Path(__file__).parent.parent.parent if '__file__' in dir() else Path('.').absolute()
sys.path.insert(0, str(project_root))

import numpy as np
import polars as pl
from MOEXPy.MOEXPy import MOEXPy
from FinLabPy.Utils import setup_logger

logger = setup_logger('futoi_portfolio')


class FutOIStrategy:
    """Торговая стратегия на основе FutOI."""
    
    def __init__(self, api, tickers=None, threshold=10_000_000):
        self.api = api
        self.tickers = tickers or ['GLDRUBF', 'CNYRUBF', 'SBERF', 'GAZPF', 'IMOEXF']
        self.threshold = threshold
        self.positions = {}
    
    def load_futoi_data(self) -> pl.DataFrame:
        """Загружает дневные данные FutOI."""
        futoi_path = project_root / 'data' / 'futoi_daily.parquet'
        
        if not futoi_path.exists():
            logger.error(f'Файл не найден: {futoi_path}')
            return pl.DataFrame()
        
        df = pl.read_parquet(futoi_path)
        logger.info(f'Загружено FutOI: {len(df)} записей, {df["ticker"].n_unique()} тикеров')
        
        # Определяем колонку с датой
        date_col = 'tradedate' if 'tradedate' in df.columns else 'date'
        if date_col in df.columns:
            logger.info(f'Даты: {df[date_col].min()} — {df[date_col].max()}')
        
        return df
    
    def get_signal(self, ticker: str, futoi_df: pl.DataFrame) -> dict:
        """Возвращает последний сигнал для тикера."""
        ticker_data = futoi_df.filter(pl.col('ticker') == ticker).sort('tradedate', descending=True)
        
        if len(ticker_data) < 2:
            return {'signal': 'HOLD', 'phys_change': 0, 'phys_net': 0}
        
        # Безопасное извлечение скалярных значений
        latest_row = ticker_data.row(0, named=True)
        prev_row = ticker_data.row(1, named=True) if len(ticker_data) > 1 else None
        
        phys_change = latest_row.get('phys_change')
        phys_net = latest_row.get('phys_net', 0)
        
        # phys_change может быть None для первой даты
        if phys_change is None:
            phys_change = 0
        
        phys_change = float(phys_change)
        phys_net = float(phys_net) if phys_net else 0
        
        if phys_change > self.threshold:
            signal = 'BUY'
        elif phys_change < -self.threshold:
            signal = 'SELL'
        else:
            signal = 'HOLD'
        
        return {
            'signal': signal,
            'phys_change': int(phys_change),
            'phys_net': int(phys_net),
            'date': latest_row.get('tradedate', ''),
            'prev_date': prev_row.get('tradedate', '') if prev_row else '',
        }
    
    def check_signals(self) -> dict:
        """Проверяет сигналы для всех тикеров."""
        futoi_df = self.load_futoi_data()
        if futoi_df.is_empty():
            return {'error': 'Нет данных FutOI'}
        
        signals = {}
        recommendations = []
        
        for ticker in self.tickers:
            signal = self.get_signal(ticker, futoi_df)
            signals[ticker] = signal
            
            if ticker in self.positions:
                if signal['signal'] == 'SELL':
                    recommendations.append({
                        'ticker': ticker,
                        'action': 'SELL',
                        'reason': f'phys_change={signal["phys_change"]:,} < -{self.threshold:,}'
                    })
            else:
                if signal['signal'] == 'BUY':
                    recommendations.append({
                        'ticker': ticker,
                        'action': 'BUY',
                        'reason': f'phys_change={signal["phys_change"]:,} > {self.threshold:,}',
                        'phys_net': signal['phys_net'],
                    })
        
        return {
            'signals': signals,
            'positions': list(self.positions.keys()),
            'recommendations': recommendations,
            'timestamp': datetime.now().isoformat(),
        }
    
    def run_daily(self):
        """Ежедневный запуск — проверка сигналов."""
        logger.info(f'{"="*60}')
        logger.info(f'FutOI СТРАТЕГИЯ — {datetime.now().strftime("%Y-%m-%d %H:%M")}')
        logger.info(f'{"="*60}')
        
        result = self.check_signals()
        
        if 'error' in result:
            logger.error(result['error'])
            return result
        
        logger.info(f'\nТекущие позиции: {result["positions"] if result["positions"] else "нет"}')
        logger.info(f'\nСигналы на сегодня:')
        for ticker, sig in result['signals'].items():
            emoji = '🟢' if sig['signal'] == 'BUY' else '🔴' if sig['signal'] == 'SELL' else '⚪'
            logger.info(f'  {emoji} {ticker}: {sig["signal"]:<5} | phys_change={sig["phys_change"]:>+15,} | phys_net={sig["phys_net"]:>+15,} | дата={sig["date"]}')
        
        logger.info(f'\nРекомендации:')
        if result['recommendations']:
            for rec in result['recommendations']:
                logger.info(f'  ▶ {rec["ticker"]}: {rec["action"]} — {rec["reason"]}')
        else:
            logger.info('  Нет новых сигналов')
        
        return result


# ============ ТЕСТ ============
if __name__ == '__main__':
    api = MOEXPy(token=os.getenv('MOEX_TOKEN'))
    strategy = FutOIStrategy(api)
    strategy.run_daily()
