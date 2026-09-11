"""
Загрузка индекса концентрации HI2 (Херфиндаля-Хиршмана) через MOEX API.
"""
import polars as pl
from datetime import datetime, timedelta, date


class HI2Loader:
    """Загружает и кэширует HI2 для списка тикеров."""
    
    def __init__(self, api):
        self.api = api
    
    def load_hi2(self, engine: str, ticker: str, days: int = 90) -> pl.DataFrame:
        """
        Загружает HI2 за N дней.
        
        Args:
            engine: 'stocks', 'futures', 'currency'
            ticker: тикер
            days: глубина истории
        
        Returns:
            DataFrame с колонками: date, hhi_agressive, hhi_volume
        """
        results = {}
        
        for i in range(days):
            d = date.today() - timedelta(days=i)
            
            try:
                raw = self.api.get_hi2(engine, ticker, d)
                
                if raw and 'data' in raw:
                    hi2_data = raw['data']
                    if 'data' in hi2_data and hi2_data['data']:
                        for row in hi2_data['data']:
                            trade_date = row[0]  # tradedate
                            metric = row[3]       # metric: hhi_agressive / hhi_volume
                            value = row[4]        # value
                            
                            if trade_date not in results:
                                results[trade_date] = {}
                            results[trade_date][metric] = int(value)
                            
            except Exception as e:
                pass  # Пропускаем дни без данных
        
        if not results:
            return pl.DataFrame()
        
        # Преобразуем в DataFrame
        rows = []
        for d, metrics in results.items():
            rows.append({
                'date': d,
                'hhi_agressive': metrics.get('hhi_agressive'),
                'hhi_volume': metrics.get('hhi_volume'),
            })
        
        df = pl.DataFrame(rows).sort('date')
        return df
    
    def load_multiple(self, engine: str, tickers: list, days: int = 90) -> pl.DataFrame:
        """Загружает HI2 для нескольких тикеров."""
        all_data = []
        
        for ticker in tickers:
            print(f'Загрузка HI2: {ticker}...')
            df = self.load_hi2(engine, ticker, days)
            
            if not df.is_empty():
                df = df.with_columns(pl.lit(ticker).alias('ticker'))
                all_data.append(df)
                print(f'  Загружено {len(df)} дней: {df["date"].min()} — {df["date"].max()}')
            else:
                print(f'  Нет данных')
        
        if not all_data:
            return pl.DataFrame()
        
        return pl.concat(all_data)


# ============ ТЕСТ ============
if __name__ == '__main__':
    import os
    import sys
    from pathlib import Path
    
    project_root = Path('.').absolute()
    sys.path.insert(0, str(project_root))
    
    from MOEXPy.MOEXPy import MOEXPy
    
    api = MOEXPy(token=os.getenv('MOEX_TOKEN'))
    loader = HI2Loader(api)
    
    # Тест: SBER за 10 дней
    print('Тест HI2: SBER (stocks) за 10 дней\n')
    df = loader.load_hi2('stocks', 'SBER', days=10)
    
    if not df.is_empty():
        print(f'\nРезультат: {len(df)} дней')
        print(df)
    else:
        print('Нет данных')
