#!/usr/bin/env python3
"""Проверка свежести всех FutOI файлов."""
import pandas as pd
from pathlib import Path
from datetime import datetime

FUTOI_DIR = Path('/root/finlab/data/futoi')
THRESHOLD_HOURS = 24

now = pd.Timestamp.now()
stale, fresh, missing = [], [], []

for f in sorted(FUTOI_DIR.glob('*_futoi.parquet')):
    ticker = f.stem.replace('_futoi', '')
    try:
        df = pd.read_parquet(f, columns=['tradedate', 'tradetime'])
        last = df.iloc[-1]
        last_dt = pd.to_datetime(f"{last['tradedate']} {last['tradetime']}")
        age_h = (now - last_dt).total_seconds() / 3600
        if age_h > THRESHOLD_HOURS:
            stale.append((ticker, age_h))
        else:
            fresh.append((ticker, age_h))
    except Exception as e:
        missing.append((ticker, str(e)))

print(f"✅ Свежие: {len(fresh)}")
print(f"⚠️ Устаревшие: {len(stale)}")
for t, a in stale[:10]:
    print(f"   {t}: {a:.1f}ч")
print(f"❌ Ошибки/нет данных: {len(missing)}")
for t, e in missing[:10]:
    print(f"   {t}: {e}")
