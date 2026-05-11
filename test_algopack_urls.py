"""Пробуем MOEXPy.check_result с Algopack URL"""
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
from requests import get

sys.path.insert(0, str(Path(__file__).parent))
from MOEXPy.MOEXPy import MOEXPy

api = MOEXPy(os.getenv('MOEX_TOKEN'))

dt_till = datetime.now()
dt_from = dt_till - timedelta(days=5)

# Пробуем разные URL префиксы для Algopack
urls = [
    f'https://iss.moex.com/iss/datashop/algopack/eq/tradestats/SBER.json',
    f'{api.iss_server}/datashop/algopack/eq/tradestats/SBER.json',
    f'https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities/SBER/tradestats.json',
]

for url in urls:
    params = {'from': dt_from.strftime('%Y-%m-%d'), 'till': dt_till.strftime('%Y-%m-%d'), 'start': 0}
    print(f'\nURL: {url}')
    try:
        resp = get(url, params=params, headers=api.headers, timeout=10)
        print(f'  Status: {resp.status_code}')
        print(f'  Content-Type: {resp.headers.get("Content-Type", "")[:50]}')
        
        if 'json' in resp.headers.get('Content-Type', ''):
            data = resp.json()
            print(f'  Keys: {list(data.keys())}')
        else:
            print(f'  Not JSON, length={len(resp.text)}')
    except Exception as e:
        print(f'  Error: {e}')
