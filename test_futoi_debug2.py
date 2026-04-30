"""
ОТЛАДКА v2: смотрим ключи словаря FutOI
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

print(f"Тип: {type(raw_data)}")
print(f"Ключи: {list(raw_data.keys())}")

for key in raw_data.keys():
    val = raw_data[key]
    print(f"\n--- {key} ---")
    print(f"  Тип: {type(val)}")
    if isinstance(val, list):
        print(f"  Длина: {len(val)}")
        if len(val) > 0:
            print(f"  Первый элемент: {val[0]}")
            if isinstance(val[0], (list, tuple)):
                print(f"  Длина первого элемента: {len(val[0])}")
                for i, item in enumerate(val[0]):
                    print(f"    [{i}]: {item}")
            elif isinstance(val[0], dict):
                print(f"  Ключи первого элемента: {list(val[0].keys())}")
                print(f"  Первый элемент: {val[0]}")
    elif isinstance(val, dict):
        print(f"  Ключи: {list(val.keys())}")
        print(f"  Пример: {val}")
    else:
        print(f"  Значение: {val}")
