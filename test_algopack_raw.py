"""Прямой запрос к Algopack с детальным логом"""
import os
import requests
from datetime import datetime, timedelta

dt_till = datetime.now()
dt_from = dt_till - timedelta(days=5)

url = 'https://iss.moex.com/iss/datashop/algopack/eq/tradestats/SBER.json'
params = {'from': dt_from.strftime('%Y-%m-%d'), 'till': dt_till.strftime('%Y-%m-%d'), 'start': 0}
headers = {'Authorization': f'Bearer {os.getenv("MOEX_TOKEN")}'}

print(f'URL: {url}')
print(f'Params: {params}')
print(f'Token prefix: {os.getenv("MOEX_TOKEN")[:50]}...')

resp = requests.get(url, params=params, headers=headers, timeout=30)

print(f'Status: {resp.status_code}')
print(f'Content-Type: {resp.headers.get("Content-Type")}')
print(f'Content-Length: {len(resp.content)}')
print(f'Raw response (first 1000 chars):')
print(resp.text[:1000])
