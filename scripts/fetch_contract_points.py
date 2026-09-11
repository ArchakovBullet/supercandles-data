#!/usr/bin/env python3
"""
Обновление contract_points.json
================================
Для фьючерсов: point_value = STEPPRICE × MINSTEP (MOEX ISS)
Для акций:     point_value = MINSTEP (шаг цены в рублях)
"""
import json
import sys
from pathlib import Path

import requests

# === Пути ===
ROOT = Path('/root/finlab')
TICKERS_CONFIG = ROOT / 'FinLabPy' / 'DataCollectors' / 'tickers_config.json'
OUTPUT_FILE = ROOT / 'robots' / 'contract_points.json'

# === MOEX ISS ===
ISS_FORTS = 'https://iss.moex.com/iss/engines/futures/markets/forts/securities.json'
ISS_SHARES = 'https://iss.moex.com/iss/engines/stock/markets/shares/securities.json'


def fetch_moex(url):
    """Загрузить данные с MOEX ISS."""
    r = requests.get(url, params={'iss.meta': 'off'}, timeout=30)
    r.raise_for_status()
    data = r.json()
    sec = data['securities']
    cols = sec['columns']
    rows = [dict(zip(cols, row)) for row in sec['data']]
    return rows


def build_futures_map(rows):
    """ASSETCODE -> {STEPPRICE, MINSTEP, LOTVOLUME, DECIMALS}."""
    result = {}
    for row in rows:
        asset = row.get('ASSETCODE')
        if not asset:
            continue
        # Берём первый (обычно ближайший) контракт
        if asset not in result:
            result[asset] = {
                'STEPPRICE': row.get('STEPPRICE'),
                'MINSTEP': row.get('MINSTEP'),
                'LOTVOLUME': row.get('LOTVOLUME'),
                'DECIMALS': row.get('DECIMALS'),
                'SECID': row.get('SECID'),
            }
    return result


def build_shares_map(rows):
    """SECID -> {MINSTEP, ...} для акций."""
    result = {}
    for row in rows:
        secid = row.get('SECID')
        if not secid:
            continue
        if secid not in result:
            result[secid] = {
                'MINSTEP': row.get('MINSTEP'),
                'DECIMALS': row.get('DECIMALS'),
                'LOTVOLUME': row.get('LOTVOLUME'),
            }
    return result


def main():
    print('=' * 60)
    print('Обновление contract_points.json')
    print('=' * 60)

    # Загружаем конфиг тикеров
    with open(TICKERS_CONFIG) as f:
        cfg = json.load(f)
    futures_tickers = cfg.get('futures', [])
    shares_tickers = cfg.get('stocks', []) or cfg.get('shares', [])

    print(f'Фьючерсов в конфиге: {len(futures_tickers)}')
    print(f'Акций в конфиге: {len(shares_tickers)}')

    # MOEX ISS
    print('\nЗагружаю MOEX ISS...')
    futures_rows = fetch_moex(ISS_FORTS)
    shares_rows = fetch_moex(ISS_SHARES)
    print(f'  Фьючерсов: {len(futures_rows)}')
    print(f'  Акций: {len(shares_rows)}')

    futures_map = build_futures_map(futures_rows)
    shares_map = build_shares_map(shares_rows)

    # Строим point_values
    result = {}
    missing = []

    # 1) Фьючерсы: point_value = STEPPRICE × MINSTEP
    for t in futures_tickers:
        # Попробовать прямое совпадение с ASSETCODE
        info = futures_map.get(t)
        if info and info['STEPPRICE'] is not None and info['MINSTEP'] is not None:
            pv = info['STEPPRICE'] * info['MINSTEP']
            result[t] = round(pv, 6)
            continue
        # Иначе — искать по SECID (например, USDRUBF, CNYRUBF — это SECID, а не ASSETCODE)
        for row in futures_rows:
            if row.get('SECID') == t:
                if row.get('STEPPRICE') is not None and row.get('MINSTEP') is not None:
                    pv = row['STEPPRICE'] * row['MINSTEP']
                    result[t] = round(pv, 6)
                    break
        else:
            missing.append(t)

    # 2) Акции: point_value = MINSTEP (шаг цены в рублях)
    for t in shares_tickers:
        info = shares_map.get(t)
        if info and info['MINSTEP'] is not None:
            result[t] = round(info['MINSTEP'], 6)
        else:
            missing.append(t)

    # Дополняем старыми значениями (если что-то не нашли — не теряем)
    if OUTPUT_FILE.exists():
        with open(OUTPUT_FILE) as f:
            old = json.load(f)
        for k, v in old.items():
            if k not in result:
                result[k] = v
                print(f'  ⚠️ {k}: сохранено старое значение {v}')

    # Сохраняем
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(result, f, indent=4, ensure_ascii=False)

    print(f'\n✅ Сохранено: {len(result)} тикеров в {OUTPUT_FILE}')
    print(f'❌ Не найдено: {len(missing)}')
    if missing:
        print('   Пропущены:', ', '.join(missing[:20]))
        if len(missing) > 20:
            print(f'   ... и ещё {len(missing) - 20}')

    # Тест на известных значениях
    print('\n=== Тест на известных значениях ===')
    expected = {
        'RI': 173.77, 'MOEXCNY': 0.1279, 'MY': 0.1279,
        'BR': 0.0869, 'GD': 0.8689, 'LKOH': 1.0,
        'SBERF': 0.01, 'USDRUBF': 0.1, 'EURRUBF': 0.1, 'GLDRUBF': 0.01,
    }
    for k, v in expected.items():
        actual = result.get(k)
        if actual is not None:
            diff = abs(actual - v) / v * 100 if v else 0
            status = '✅' if diff < 20 else '⚠️'
            print(f'  {status} {k}: ожидалось ~{v}, получено {actual} (откл. {diff:.1f}%)')
        else:
            print(f'  ❌ {k}: не найдено')


if __name__ == '__main__':
    main()
