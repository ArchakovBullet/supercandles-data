"""Сборщик LQDT — безрисковый бенчмарк (фонд ликвидности MOEX)."""
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from MOEXPy.MOEXPy import MOEXPy
import os

api = MOEXPy(token=os.getenv('MOEX_TOKEN'))
OUT = Path('/root/finlab/data/candles/LQDT_D1.parquet')

# Собрать M10 свечи
end = datetime.now()
start = end - timedelta(days=7)  # Последние 7 дней
result = api.get_candles('TQBR', 'LQDT', start, end, 'M10')
df = pd.DataFrame(result['candles']['data'], columns=result['candles']['columns'])
df['begin'] = pd.to_datetime(df['begin'])
df['date'] = df['begin'].dt.date

# Агрегировать в D1
daily = df.groupby('date').agg(
    open=('open','first'), close=('close','last'),
    high=('high','max'), low=('low','min'), volume=('volume','sum')
).reset_index()
daily['begin'] = pd.to_datetime(daily['date'].astype(str) + ' 00:00:00')
daily['end'] = pd.to_datetime(daily['date'].astype(str) + ' 23:59:59')
daily['value'] = 0
daily = daily[['open','close','high','low','value','volume','begin','end']]

# Объединить с историей
if OUT.exists():
    old = pd.read_parquet(OUT)
    old['begin'] = pd.to_datetime(old['begin'])
    combined = pd.concat([old, daily]).drop_duplicates('begin').sort_values('begin')
else:
    combined = daily

combined.to_parquet(OUT, index=False)
print(f'LQDT: {len(combined)} дневных свечей, последняя: {combined["close"].iloc[-1]}')
