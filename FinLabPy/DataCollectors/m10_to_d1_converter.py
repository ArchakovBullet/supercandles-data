"""
Конвертер 10-минутных свечей MOEX в дневные + метрики из обезличенных сделок.
"""
import polars as pl
from datetime import datetime, timedelta


class M10ToD1Converter:
    """Конвертирует 10-минутные свечи MOEX в дневные с метриками."""
    
    def __init__(self, api):
        self.api = api
    
    def load_candles(self, board: str, ticker: str, days: int = 90) -> pl.DataFrame:
        dt_till = datetime.now()
        dt_from = dt_till - timedelta(days=days)
        
        raw = self.api.get_candles(board, ticker, dt_from, dt_till, 'D1')
        data = raw['candles']['data']
        columns = raw['candles']['columns']
        
        df = pl.DataFrame([
            pl.Series(col, [row[i] for row in data])
            for i, col in enumerate(columns)
        ])
        
        df = df.with_columns([
            pl.col('open').cast(pl.Float64),
            pl.col('close').cast(pl.Float64),
            pl.col('high').cast(pl.Float64),
            pl.col('low').cast(pl.Float64),
            pl.col('value').cast(pl.Float64),
            pl.col('volume').cast(pl.Int64),
            pl.col('begin').str.strptime(pl.Datetime, format='%Y-%m-%d %H:%M:%S'),
            pl.col('end').str.strptime(pl.Datetime, format='%Y-%m-%d %H:%M:%S'),
        ])
        
        return df
    
    def load_trades(self, board: str, ticker: str, days: int = 90) -> pl.DataFrame:
        dt_till = datetime.now()
        dt_from = dt_till - timedelta(days=days)
        
        raw = self.api.get_trades(board, ticker, dt_from, dt_till)
        
        if not raw or 'trades' not in raw:
            return pl.DataFrame()
        
        data = raw['trades']['data']
        columns = raw['trades']['columns']
        
        df = pl.DataFrame([
            pl.Series(col, [row[i] for row in data])
            for i, col in enumerate(columns)
        ])
        
        df = df.with_columns([
            pl.col('tradetime').str.strptime(pl.Datetime, format='%Y-%m-%d %H:%M:%S'),
            pl.col('price').cast(pl.Float64),
            pl.col('quantity').cast(pl.Int64),
        ])
        
        return df
    
    def aggregate_trades_to_daily(self, trades_df: pl.DataFrame) -> pl.DataFrame:
        if trades_df.is_empty():
            return pl.DataFrame()
        
        trades_df = trades_df.with_columns(
            pl.col('tradetime').dt.date().alias('date')
        )
        
        trades_df = trades_df.with_columns(
            (pl.col('price') * pl.col('quantity')).alias('volume')
        )
        
        buy_df = trades_df.filter(pl.col('buysell') == 'B')
        sell_df = trades_df.filter(pl.col('buysell') == 'S')
        
        daily = trades_df.group_by('date').agg([
            pl.len().alias('trades_count'),
            pl.col('volume').sum().alias('total_volume'),
            pl.col('quantity').sum().alias('total_quantity'),
        ])
        
        buy_daily = buy_df.group_by('date').agg([
            pl.col('volume').sum().alias('buy_volume'),
            pl.len().alias('buy_trades'),
        ])
        
        sell_daily = sell_df.group_by('date').agg([
            pl.col('volume').sum().alias('sell_volume'),
            pl.len().alias('sell_trades'),
        ])
        
        daily = daily.join(buy_daily, on='date', how='left')
        daily = daily.join(sell_daily, on='date', how='left')
        
        daily = daily.with_columns([
            pl.col('buy_volume').fill_null(0),
            pl.col('sell_volume').fill_null(0),
            pl.col('buy_trades').fill_null(0),
            pl.col('sell_trades').fill_null(0),
        ])
        
        daily = daily.with_columns([
            (pl.col('buy_volume') - pl.col('sell_volume')).alias('imbalance'),
            (pl.col('buy_volume') / (pl.col('buy_volume') + pl.col('sell_volume'))).alias('buy_ratio'),
        ])
        
        daily = daily.with_columns(
            pl.col('buy_ratio').fill_null(0.5)
        )
        
        return daily
    
    def aggregate_candles_to_daily(self, candles_df: pl.DataFrame) -> pl.DataFrame:
        daily = candles_df.group_by(
            pl.col('begin').dt.date().alias('date')
        ).agg([
            pl.col('open').first().alias('open'),
            pl.col('high').max().alias('high'),
            pl.col('low').min().alias('low'),
            pl.col('close').last().alias('close'),
            pl.col('volume').sum().alias('volume'),
            pl.col('value').sum().alias('value'),
            pl.len().alias('bars_count'),
        ]).sort('date')
        
        return daily
    
    def convert(self, board: str, ticker: str, days: int = 90, include_trades: bool = True) -> pl.DataFrame:
        print(f'Загрузка свечей {ticker} ({board}) за {days} дней...')
        candles = self.load_candles(board, ticker, days)
        print(f'  Загружено свечей: {len(candles)}')
        
        print('Агрегация в дневные...')
        daily = self.aggregate_candles_to_daily(candles)
        print(f'  Получено дней: {len(daily)}')
        
        if include_trades:
            print('Загрузка обезличенных сделок...')
            trades = self.load_trades(board, ticker, days)
            print(f'  Загружено сделок: {len(trades)}')
            
            if not trades.is_empty():
                trades_daily = self.aggregate_trades_to_daily(trades)
                daily = daily.join(trades_daily, on='date', how='left')
                print('  Добавлено метрик: imbalance, buy_ratio, ...')
            else:
                print('  Сделки не загружены — пропускаем метрики')
        
        return daily


# ============ ТЕСТ ============
if __name__ == '__main__':
    import os
    import sys
    from pathlib import Path
    
    project_root = Path('.').absolute()
    sys.path.insert(0, str(project_root))
    
    from MOEXPy.MOEXPy import MOEXPy
    
    api = MOEXPy(token=os.getenv('MOEX_TOKEN'))
    converter = M10ToD1Converter(api)
    
    df = converter.convert('TQBR', 'SBER', days=90, include_trades=False)
    
    print(f'\n{"="*60}')
    print(f'РЕЗУЛЬТАТ: {df.shape[0]} дней, {df.shape[1]} колонок')
    print(f'Колонки: {df.columns}')
    print(f'Диапазон дат: {df["date"].min()} — {df["date"].max()}')
    print(f'\nПервые 3 дня:')
    print(df.head(3))
    print(f'\nПоследние 3 дня:')
    print(df.tail(3))
