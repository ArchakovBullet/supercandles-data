#!/usr/bin/env python3
"""Обновление кеша LASTTRADEDATE для фьючерсов (MOEX ISS)."""
import json
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv('/root/finlab/.env')

ROOT = Path('/root/finlab')
CC_PATH = ROOT / 'FinLabPy' / 'DataCollectors' / 'contract_cache.json'
CACHE_PATH = ROOT / 'robots' / 'contract_last_tradedate.json'

with open(CC_PATH) as f:
    cc = json.load(f)

codes = []
for ticker, v in cc.items():
    code = v.get('code')
    if code:
        codes.append(code)

print(f'Всего кодов: {len(codes)}')

cache = {}
for i in range(0, len(codes), 50):
    batch = codes[i:i+50]
    url = ('https://iss.moex.com/iss/engines/futures/markets/forts/securities.json'
           f'?iss.meta=off&securities={",".join(batch)}')
    try:
        r = requests.get(url, timeout=15)
        data = r.json()
        cols = data['securities']['columns']
        for row in data['securities']['data']:
            secid = row[cols.index('SECID')]
            last = row[cols.index('LASTTRADEDATE')] if 'LASTTRADEDATE' in cols else None
            cache[secid] = last
    except Exception as e:
        print(f'Ошибка batch {i}: {e}')

with open(CACHE_PATH, 'w') as f:
    json.dump(cache, f, indent=2, ensure_ascii=False)

print(f'✅ Кеш сохранён: {CACHE_PATH} ({len(cache)} записей)')

# Показываем примеры
for t in ['GD', 'PT', 'NG', 'NR']:
    code = cc.get(t, {}).get('code')
    last = cache.get(code, 'НЕТ')
    print(f'  {t} ({code}): {last}')
