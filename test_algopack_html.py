"""Разбор HTML-ответа от Algopack"""
import os
import requests
from datetime import datetime, timedelta
import re

dt_till = datetime.now()
dt_from = dt_till - timedelta(days=5)

url = 'https://iss.moex.com/iss/datashop/algopack/eq/tradestats/SBER.json'
headers = {'Authorization': f'Bearer {os.getenv("MOEX_TOKEN")}'}

# Пробуем разные варианты параметров
for params in [
    {'from': dt_from.strftime('%Y-%m-%d'), 'till': dt_till.strftime('%Y-%m-%d'), 'start': 0},
    {'date': dt_till.strftime('%Y-%m-%d')},
    {},
]:
    print(f'\nParams: {params}')
    resp = requests.get(url, params=params, headers=headers, timeout=10)
    print(f'Status: {resp.status_code}, Length: {len(resp.text)}')
    
    # Извлекаем сообщение из HTML
    if 'text/html' in resp.headers.get('Content-Type', ''):
        # Ищем текст ошибки
        text = re.sub(r'<[^>]+>', ' ', resp.text)
        text = re.sub(r'\s+', ' ', text).strip()
        # Ищем ключевые фразы
        for keyword in ['error', 'Error', 'ошибк', 'доступ', 'access', 'denied', 'forbidden', 'not found']:
            idx = text.lower().find(keyword)
            if idx > 0:
                print(f'  Сообщение: ...{text[max(0,idx-50):idx+100]}...')
                break
        else:
            print(f'  Текст: {text[:300]}')
    else:
        print(f'  Ответ: {resp.text[:300]}')
