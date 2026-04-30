"""
ОТЛАДКА: смотрим структуру данных FutOI API
"""
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from MOEXPy.MOEXPy import MOEXPy

# 1. Проверяем токен
token = os.getenv('MOEX_TOKEN')
print(f"Токен есть: {bool(token)}")
print(f"Длина токена: {len(token) if token else 0}")

# 2. Создаем API с токеном
api = MOEXPy(token=token)

# 3. Пробуем получить данные
dt_till = datetime.now()
dt_from = dt_till - timedelta(days=3)

print(f"\nЗапрос: GLDRUBF, {dt_from} - {dt_till}")

try:
    raw_data = api.get_futoi('GLDRUBF', dt_from, dt_till)
    print(f"\nТип данных: {type(raw_data)}")
    print(f"Длина: {len(raw_data) if raw_data else 0}")
    
    if raw_data and len(raw_data) > 0:
        print(f"\nПервая запись:")
        print(f"  Тип: {type(raw_data[0])}")
        print(f"  Длина: {len(raw_data[0])}")
        print(f"  Содержимое: {raw_data[0]}")
        
        print(f"\nВсего записей: {len(raw_data)}")
        
        # Пробуем разные индексы
        for i, val in enumerate(raw_data[0]):
            print(f"  [{i}]: {val} (type: {type(val).__name__})")
    else:
        print("Пустой ответ!")
        
except Exception as e:
    print(f"Ошибка: {e}")
    import traceback
    traceback.print_exc()
