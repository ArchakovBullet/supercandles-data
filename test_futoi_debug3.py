"""
Финальная отладка: мапим индексы на названия колонок
"""
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from MOEXPy.MOEXPy import MOEXPy

token = os.getenv('MOEX_TOKEN')
api = MOEXPy(token=token)

dt_till = datetime.now()
dt_from = dt_till - timedelta(days=3)

raw_data = api.get_futoi('GLDRUBF', dt_from, dt_till)

# Берем первую запись
first = raw_data['futoi.data'][0]
print("Индексы первой записи:")
for i, val in enumerate(first):
    print(f"  [{i}] = {val} (type: {type(val).__name__})")

# Смотрим все даты
print(f"\nДаты: {raw_data['futoi.dates']['data']}")
