"""Сохраняем образец tradestats для разбора структуры"""
import os
import requests
from datetime import datetime, timedelta
import json

token = os.getenv('MOEX_TOKEN')
headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}

dt_till = datetime.now()
dt_from = dt_till - timedelta(days=1)

url = 'https://apim.moex.com/iss/datashop/algopack/eq/tradestats/SBER.json'
params = {'from': dt_from.strftime('%Y-%m-%d'), 'till': dt_till.strftime('%Y-%m-%d'), 'start': 0}

resp = requests.get(url, params=params, headers=headers, timeout=30)
data = resp.json()

# Сохраняем для изучения
with open('super_candles_sample.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

# Показываем структуру
print('Ключи:', list(data.keys()))
for key in data:
    val = data[key]
    if 'columns' in val:
        print(f'\n{key}.columns:')
        for i, col in enumerate(val['columns']):
            print(f'  [{i}] {col}')
    if 'data' in val and val['data']:
        print(f'{key}.data[0]: {val["data"][0]}')
print('\nОбразец сохранён в super_candles_sample.json')
