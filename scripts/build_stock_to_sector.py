#!/usr/bin/env python3
"""
Построение мапы: тикер акции → отраслевой индекс MOEX.
Источник: MOEX ISS (statistics/engines/stock/markets/index/analytics/{INDEX}/tickers).
"""
import json
import requests
from pathlib import Path
from datetime import datetime

SECTORS = [
    'MOEXOG',  # Нефть и газ
    'MOEXFN',  # Финансы
    'MOEXMM',  # Металлы и добыча
    'MOEXEU',  # Электроэнергетика
    'MOEXTL',  # Телеком
    'MOEXCH',  # Химия
    'MOEXCN',  # Потребительский
    'MOEXIT',  # IT
    'MOEXRE',  # Недвижимость
    'MOEXTN',  # Транспорт
]

OUTPUT = Path('/root/finlab/robots/stock_to_sector.json')


def get_index_composition(index):
    """Получить актуальный состав индекса через MOEX ISS."""
    url = f'https://iss.moex.com/iss/statistics/engines/stock/markets/index/analytics/{index}/tickers.json'
    params = {'iss.meta': 'off'}
    try:
        r = requests.get(url, params=params, timeout=30)
        if r.status_code != 200:
            print(f'  ⚠️ {index}: HTTP {r.status_code}')
            return []
        data = r.json()
    except Exception as e:
        print(f'  ❌ {index}: {e}')
        return []

    if 'tickers' not in data:
        return []

    rows = data['tickers']['data']
    cols = data['tickers']['columns']

    i_ticker = cols.index('ticker')
    i_from = cols.index('from')
    i_till = cols.index('till')

    from datetime import timedelta
    today_dt = datetime.now()
    today = today_dt.strftime('%Y-%m-%d')
    # Ослабленный фильтр: till >= today - 30 дней
    min_till = (today_dt - timedelta(days=30)).strftime('%Y-%m-%d')

    active = []
    for row in rows:
        ticker = row[i_ticker]
        from_date = row[i_from]
        till_date = row[i_till]
        # Активная: from <= today И till >= (today - 30)
        if from_date <= today and till_date >= min_till:
            active.append(ticker)

    return active


# Жёсткая мапа для акций, не покрытых индексами MOEX
HARDCODED = {
    'AFKS': 'MOEXTL',   # АФК Система (телеком/холдинг)
    'MTSS': 'MOEXTL',   # МТС (телеком)
    'RTKM': 'MOEXTL',   # Ростелеком (телеком)
    'YDEX': 'MOEXIT',   # Яндекс (IT)
    'VKCO': 'MOEXIT',   # VK (IT)
    'POSI': 'MOEXIT',   # Positive Technologies (IT)
    'ASTR': 'MOEXIT',   # Astra Linux (IT)
    'OZON': 'MOEXCN',   # OZON (потреб)
    'MVID': 'MOEXCN',   # М.Видео (потреб)
    'SMLT': 'MOEXRE',   # Самолет (недвижимость)
    'SGZH': 'MOEXMM',   # Сегежа (лес/металлы)
    'HHRU': 'MOEXIT',   # HeadHunter (IT/HR)
    'RNFT': 'MOEXOG',   # РуссНефть (нефть)
    'SIBN': 'MOEXOG',   # Газпром нефть (нефть)
}


def build_map():
    result = dict(HARDCODED)  # начинаем с hardcoded
    conflicts = {}

    for sector in SECTORS:
        tickers = get_index_composition(sector)
        print(f'  {sector}: {len(tickers)} активных')

        for t in tickers:
            if t not in result:
                result[t] = sector
            else:
                # Конфликт: тикер в 2 индексах
                conflicts.setdefault(t, [result[t]]).append(sector)

    # Сохраняем
    OUTPUT.parent.mkdir(exist_ok=True)
    with open(OUTPUT, 'w') as f:
        json.dump({
            'updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'source': 'MOEX ISS',
            'sectors': result,
            'conflicts': conflicts,
        }, f, ensure_ascii=False, indent=2)

    print(f'\n✅ Тикеров с сектором: {len(result)}')
    if conflicts:
        print(f'⚠️ Конфликтов: {len(conflicts)}')
        for t, secs in list(conflicts.items())[:10]:
            print(f'  {t}: {secs}')

    return result


if __name__ == '__main__':
    print('=== Построение stock_to_sector.json ===')
    result = build_map()
    print()
    print('Примеры:')
    for t in list(result.keys())[:20]:
        print(f'  {t}: {result[t]}')
