#!/usr/bin/env python3
"""Проверить распределение yur_buy и правильные пороги."""
import pandas as pd
from pathlib import Path

DATA_ROOT = Path('/root/finlab/data')

for tf, path in [('H4', 'futoi_4h/futoi_4h.parquet'), ('H1', 'futoi_1h/futoi_1h.parquet')]:
    futoi = pd.read_parquet(DATA_ROOT / path)
    print(f'=== {tf}: yur_buy_ratio ===')
    print(futoi['yur_buy_ratio'].describe())
    print()
    print('Квантили:')
    for q in [0.1, 0.25, 0.5, 0.75, 0.9, 0.95]:
        val = futoi['yur_buy_ratio'].quantile(q)
        print(f'  {q*100:.0f}%: {val:.1f}')
    print()
