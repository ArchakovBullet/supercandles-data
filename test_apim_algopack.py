"""Правильный URL для Algopack"""
import os
import requests
from datetime import datetime, timedelta

token = os.getenv('MOEX_TOKEN')
headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}

dt_till = datetime.now()
dt_from = dt_till - timedelta(days=5)

# Правильный URL как для FutOI
url = 'https://apim.moex.com/iss/datashop/algopack/eq/tradestats/SBER.json'
params = {'from': dt_from.strftime('%Y-%m-%d'), 'till': dt_till.strftime('%Y-%m-%d'), 'start': 0}

print(f'URL: {url}')
resp = requests.get(url, params=params, headers=headers, timeout=30)
print(f'Status: {resp.status_code}')
print(f'Content-Type: {resp.headers.get("Content-Type")}')
print(f'Length: {len(resp.content)}')

if 'json' in resp.headers.get('Content-Type', ''):
    data = resp.json()
    print(f'Keys: {list(data.keys())}')
    for key in data:
        val = data[key]
        if isinstance(val, dict) and 'data' in val:
            print(f'  {key}.data: {len(val["data"])} rows')
            if val['data']:
                print(f'  {key}.data[0]: {val["data"][0]}')
        elif isinstance(val, dict) and 'columns' in val:
            print(f'  {key}.columns: {val["columns"]}')
else:
    # Может быть просто текст ошибки
    print(f'Response: {resp.text[:500]}')
