#!/usr/bin/env python3
"""
Проверка работы всех сборщиков и агрегаторов.
"""
import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path('/root/finlab')
LOGS = ROOT / 'logs'
DATA = ROOT / 'data'

# === ВСЕ СБОРЩИКИ (cron-логи) ===
COLLECTORS = {
    'futoi_collect': ('futoi_collect_cron.log', DATA / 'futoi', 24),
    'candles_collect': ('candles_collect_cron.log', DATA / 'candles', 4),
    'hi2_collect': ('hi2_collect_cron.log', DATA / 'hi2', 24),
    'supercandles_collect': ('supercandles_collect_cron.log', DATA / 'supercandles', 24),
    'funding_collect': ('funding_collect_cron.log', DATA / 'funding', 24),
    'tradestats_collect': ('tradestats_collect_cron.log', DATA / 'tradestats', 24),
    'mega_alert': ('mega_alert_cron.log', DATA / 'mega_alerts', 24),
    'sector_indices': ('sector_indices_cron.log', DATA / 'sector_indices', 24),
}

# === АГРЕГАТОРЫ ===
AGGREGATORS = {
    'futoi_1h': ('futoi_1h_cron.log', DATA / 'futoi_1h' / 'futoi_1h.parquet', 4),
    'futoi_4h': ('futoi_4h_cron.log', DATA / 'futoi_4h' / 'futoi_4h.parquet', 12),
    'futoi_daily': ('futoi_aggregate_cron.log', DATA / 'futoi_daily.parquet', 24),
    'hi2_daily': ('hi2_aggregate_cron.log', DATA / 'hi2_daily.parquet', 24),
    'supercandles_daily': ('supercandles_aggregate_cron.log', DATA / 'supercandles_daily.parquet', 24),
    'supercandles_h4': ('supercandles_h4_aggregate_cron.log', DATA / 'supercandles_h4', 25),
}


def check_log(log_name):
    """Проверить лог на ошибки."""
    path = LOGS / log_name
    if not path.exists():
        return None, 'нет лога'

    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    # Ошибки
    errors = [l for l in content.splitlines() if 'ERROR' in l]

    # Последняя строка
    last_lines = [l for l in content.splitlines() if l.strip()][-3:]

    return errors, last_lines


def check_data_fresh(path, max_age_hours):
    """Проверить свежесть файла."""
    if not path.exists():
        return None, 'нет данных'

    mtime = datetime.fromtimestamp(path.stat().st_mtime)
    age_hours = (datetime.now() - mtime).total_seconds() / 3600

    if age_hours > max_age_hours:
        return f'{age_hours:.1f}ч', f'УСТАРЕЛО (>{max_age_hours}ч)'
    return f'{age_hours:.1f}ч', 'OK'


def main():
    print('=' * 70)
    print(f'ПРОВЕРКА СБОРЩИКОВ И АГРЕГАТОРОВ | {datetime.now().strftime("%Y-%m-%d %H:%M")}')
    print('=' * 70)

    print('\n### СБОРЩИКИ ###\n')
    for name, (log, data_path, max_age) in COLLECTORS.items():
        errors, last = check_log(log)
        if errors is None:
            print(f'❌ {name}: нет лога ({log})')
            continue

        # Свежесть
        if data_path.is_dir():
            files = list(data_path.glob('*.parquet'))
            if files:
                newest = max(files, key=lambda f: f.stat().st_mtime)
                age_str, age_status = check_data_fresh(newest, max_age)
            else:
                age_str, age_status = '—', 'нет файлов'
        elif data_path.exists():
            age_str, age_status = check_data_fresh(data_path, max_age)
        else:
            age_str, age_status = '—', 'нет данных'

        # Ошибки
        err_count = len(errors)
        err_status = '🔴' if err_count > 10 else ('⚠️' if err_count > 0 else '✅')

        print(f'{err_status} {name:<22} ошибок: {err_count:>6} | данные: {age_status} ({age_str})')

        # Показать последние уникальные ошибки
        if err_count > 0 and err_count < 20:
            unique = set(errors[-3:])
            for e in list(unique)[:2]:
                print(f'     {e[:100]}')

    print('\n### АГРЕГАТОРЫ ###\n')
    for name, (log, data_path, max_age) in AGGREGATORS.items():
        errors, last = check_log(log)
        if errors is None:
            print(f'❌ {name}: нет лога ({log})')
            continue

        age_str, age_status = check_data_fresh(data_path, max_age) if data_path.exists() else ('—', 'нет данных')
        err_count = len(errors)
        err_status = '🔴' if err_count > 10 else ('⚠️' if err_count > 0 else '✅')

        print(f'{err_status} {name:<22} ошибок: {err_count:>6} | данные: {age_status} ({age_str})')

    print('\n' + '=' * 70)


if __name__ == '__main__':
    main()
