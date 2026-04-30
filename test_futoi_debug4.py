"""
Смотрим ВСЕ ключи на верхнем уровне
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

print("=== ВСЕ КЛЮЧИ ===")
for key in raw_data.keys():
    val = raw_data[key]
    print(f"\nКлюч: '{key}'")
    print(f"  Тип: {type(val)}")
    if isinstance(val, dict):
        print(f"  Подключи: {list(val.keys())}")
    elif isinstance(val, list):
        print(f"  Длина: {len(val)}")
        if len(val) > 0:
            print(f"  Первый элемент: {val[0]}")

print("\n=== ВСЁ ДЕРЕВО ===")
def show_tree(obj, indent=0):
    if isinstance(obj, dict):
        for k in obj:
            print("  " * indent + f"'{k}': {type(obj[k]).__name__}")
            if isinstance(obj[k], (dict, list)):
                show_tree(obj[k], indent + 1)
    elif isinstance(obj, list) and len(obj) > 0:
        print("  " * indent + f"[0..{len(obj)-1}]: {type(obj[0]).__name__}")
        if isinstance(obj[0], (dict, list)):
            show_tree(obj[0], indent + 1)

show_tree(raw_data)
