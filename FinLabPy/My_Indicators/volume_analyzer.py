"""
Volume Spike Detector — обнаружение аномалий объёма.
Саймонсовский подход: volume spike → последующее движение цены.
"""
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta

DATA_ROOT = Path('/root/finlab/data')


class VolumeAnomalyDetector:
    """Обнаружение аномалий объема."""
    
    def __init__(self, window=20, threshold=2.5):
        self.window = window
        self.threshold = threshold
    
    def detect_spikes(self, volume_series: pd.Series):
        """Находит volume spikes через Z-score."""
        rolling_mean = volume_series.rolling(self.window).mean()
        rolling_std = volume_series.rolling(self.window).std()
        
        z_scores = (volume_series - rolling_mean) / rolling_std
        spikes = z_scores > self.threshold
        
        return {
            'z_scores': z_scores,
            'spikes': spikes,
            'spike_dates': volume_series.index[spikes].tolist()
        }
    
    def correlate_with_price(self, volume_spikes: pd.Series, price_returns: pd.Series, forward_days=5):
        """
        Проверить, приводят ли volume spikes к значимым ценовым движениям.
        Возвращает статистику по дням после спайка.
        """
        # Будущая доходность
        future_returns = price_returns.shift(-forward_days)
        
        spike_returns = future_returns[volume_spikes].dropna()
        normal_returns = future_returns[~volume_spikes].dropna()
        
        if len(spike_returns) < 3 or len(normal_returns) < 3:
            return None
        
        return {
            'spike_avg_return': round(spike_returns.mean(), 2),
            'normal_avg_return': round(normal_returns.mean(), 2),
            'spike_win_rate': round((spike_returns > 0).mean() * 100, 1),
            'normal_win_rate': round((normal_returns > 0).mean() * 100, 1),
            'spike_count': len(spike_returns),
            'normal_count': len(normal_returns),
            'significant': abs(spike_returns.mean() - normal_returns.mean()) > 0.5
        }
    
    def analyze_ticker(self, ticker):
        """Полный анализ аномалий объёма для тикера."""
        d1_file = DATA_ROOT / 'candles' / f'{ticker}_D1.parquet'
        if not d1_file.exists():
            return None
        
        df = pd.read_parquet(d1_file)
        if len(df) < self.window + 10:
            return None
        
        df['return'] = df['close'].pct_change() * 100
        
        # Volume spikes
        if 'volume' not in df.columns:
            return None
        
        result = self.detect_spikes(df['volume'])
        corr = self.correlate_with_price(result['spikes'], df['return'])
        
        return {
            'ticker': ticker,
            'n_spikes': len(result['spike_dates']),
            'last_spike': str(result['spike_dates'][-1])[:10] if result['spike_dates'] else None,
            'correlation': corr
        }


def scan_all_tickers():
    """Сканирует все тикеры на volume spikes."""
    detector = VolumeAnomalyDetector()
    tickers = ['CNYRUBF','EURRUBF','GAZPF','GLDRUBF','IMOEXF','SBERF','USDRUBF',
               'BR','GD','MX','RI','SI','SV','VI','W4','ED','PT','Eu','PD']
    
    print(f"{'Тикер':12} {'Спайков':>8} {'Spike Win':>10} {'Normal Win':>10} {'Значим?':>8}")
    print("-" * 55)
    
    results = []
    for t in tickers:
        r = detector.analyze_ticker(t)
        if r and r['correlation']:
            c = r['correlation']
            sig = "ДА" if c['significant'] else "—"
            print(f"{t:12} {r['n_spikes']:>8} {c['spike_win_rate']:>9.1f}% {c['normal_win_rate']:>9.1f}% {sig:>8}")
            results.append(r)
    
    return results


if __name__ == '__main__':
    print("=" * 60)
    print("VOLUME SPIKE DETECTOR — поиск аномалий объёма")
    print(f"Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    scan_all_tickers()
