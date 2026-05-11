"""Добавляем методы Super Candles в MOEXPy"""
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent))
from MOEXPy.MOEXPy import MOEXPy

api = MOEXPy(os.getenv('MOEX_TOKEN'))

# Проверяем, что уже есть в API
print(f"headers: {list(api.headers.keys())}")
print(f"iss_server: {api.iss_server}")

# Пробуем прямой запрос к Algopack
import requests
from requests import get

dt_till = datetime.now()
dt_from = dt_till - timedelta(days=5)

# URL для Algopack tradestats (акции = eq)
url = f'https://iss.moex.com/iss/datashop/algopack/eq/tradestats/SBER.json'
params = {
    'from': dt_from.strftime('%Y-%m-%d'),
    'till': dt_till.strftime('%Y-%m-%d'),
    'start': 0
}
headers = {
    'Authorization': f'Bearer {os.getenv("MOEX_TOKEN")}'
}

print(f'\nПрямой запрос: {url}')
print(f'Параметры: {params}')

resp = get(url, params=params, headers=headers)
print(f'Статус: {resp.status_code}')
if resp.status_code == 200:
    data = resp.json()
    print(f'Ключи: {list(data.keys())}')
    if 'tradestats' in data:
        ts = data['tradestats']
        print(f'Колонки: {ts["columns"]}')
        print(f'Записей: {len(ts["data"])}')
        if ts['data']:
            print(f'Первая: {ts["data"][0]}')
else:
    print(f'Ошибка: {resp.text[:500]}')
