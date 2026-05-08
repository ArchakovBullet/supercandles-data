"""
Загрузчик свечей из OsEngine (txt формат).
Формат: YYYYMMDD,HHMMSS,OPEN,HIGH,LOW,CLOSE,VOLUME,0
"""
import polars as pl
from pathlib import Path

class OsEngineLoader:
    """Загружает свечи из txt файлов OsEngine."""
    
    def __init__(self, base_path='Data_OsEngine/Set_ForAlgopack'):
        self.base_path = Path(base_path)
    
    def list_instruments(self):
        return sorted([d.name for d in self.base_path.iterdir() if d.is_dir()])
    
    def find_file(self, instrument: str):
        for d in self.base_path.iterdir():
            if d.is_dir() and instrument in d.name:
                for f in d.rglob('*.txt'):
                    if 'Settings' not in f.name:
                        return f
        raise FileNotFoundError(f'Not found: {instrument}')
    
    def load(self, instrument: str) -> pl.DataFrame:
        filepath = self.find_file(instrument)
        
        # Читаем все строки
        with open(filepath) as fh:
            lines = fh.readlines()
        
        # Парсим вручную
        rows = []
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split(',')
            if len(parts) >= 7:
                try:
                    dt = parts[0] + parts[1]  # YYYYMMDDHHMMSS
                    rows.append({
                        'datetime': dt,
                        'open': float(parts[2]),
                        'high': float(parts[3]),
                        'low': float(parts[4]),
                        'close': float(parts[5]),
                        'volume': int(float(parts[6])),  # int(float()) на случай дробных
                    })
                except (ValueError, IndexError):
                    continue
        
        if not rows:
            return pl.DataFrame()
        
        df = pl.DataFrame(rows)
        df = df.with_columns(
            pl.col('datetime').str.strptime(pl.Datetime, format='%Y%m%d%H%M%S')
        ).sort('datetime')
        
        return df
    
    def to_daily(self, df: pl.DataFrame) -> pl.DataFrame:
        return df.group_by(
            pl.col('datetime').dt.date().alias('date')
        ).agg([
            pl.col('open').first().alias('open'),
            pl.col('high').max().alias('high'),
            pl.col('low').min().alias('low'),
            pl.col('close').last().alias('close'),
            pl.col('volume').sum().alias('volume'),
            pl.len().alias('bars'),
        ]).sort('date')
    
    def info(self, instrument: str = None):
        if instrument:
            df = self.load(instrument)
            daily = self.to_daily(df)
            if len(daily) > 0:
                print(f'{instrument}: {len(df)} свечей, {len(daily)} дней')
                print(f'  Период: {daily["date"].min()} — {daily["date"].max()}')
                print(f'  Цены: {daily["close"].min():.2f} — {daily["close"].max():.2f}')
            return df, daily
        else:
            print(f'Инструментов: {len(self.list_instruments())}')
            for name in self.list_instruments():
                df = self.load(name)
                daily = self.to_daily(df)
                print(f'  {name:20s}: {len(daily):4d}д, {daily["date"].min()} — {daily["date"].max()}')
            return None, None


if __name__ == '__main__':
    loader = OsEngineLoader()
    
    print('=== ДОСТУПНЫЕ ИНСТРУМЕНТЫ ===')
    loader.info()
    
    print('\n=== GLDRUBF ДЕТАЛЬНО ===')
    loader.info('GLDRUBF(вечный)')
    
    print('\n=== АКЦИИ (сравнение с MOEX API) ===')
    for name in ['Аэрофлот', 'ВТБ ао', 'ЛУКОЙЛ', 'МосБиржа', 'Роснефть', 'Polymetal']:
        df, daily = loader.info(name)
        if daily is not None and len(daily) > 0:
            last = daily.tail(1)
            print(f'  Последняя: {last["date"][0]} close={last["close"][0]:.2f}')
