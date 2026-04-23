"""
Исправленный скрипт получения FutOI с разделением на физ. и юр. лиц
"""

import os
import sys
import warnings
warnings.filterwarnings('ignore')

# Блокируем stderr на время импорта MOEXPy
import io
old_stderr = sys.stderr
sys.stderr = io.StringIO()

from MOEXPy.MOEXPy import MOEXPy
from datetime import datetime, timedelta
import pandas as pd

# Возвращаем stderr
sys.stderr = old_stderr

# ============================================================
# НАСТРОЙКИ
# ============================================================
TICKER = 'GLDRUBF'
BOARD = 'RFUD'
DAYS = 5

# ============================================================
# ИНИЦИАЛИЗАЦИЯ
# ============================================================
token = os.getenv('MOEX_TOKEN')
if not token:
    raise ValueError("❌ Токен MOEX не найден!")

print('🔑 Инициализация MOEXPy...')
api = MOEXPy(token=token)

# ============================================================
# 1. СВЕЧИ
# ============================================================
print(f'\n📈 ЗАГРУЗКА СВЕЧЕЙ {TICKER}')
print('=' * 70)

moex_tf = api.timeframe_to_moex_timeframe('D1')
dt_from = datetime.now() - timedelta(days=DAYS)
dt_till = datetime.now()

candles = api.get_candles(BOARD, TICKER, dt_from, dt_till, moex_tf)

col_idx = {col: idx for idx, col in enumerate(candles['candles']['columns'])}
candle_data = []
for row in candles['candles']['data']:
    candle_data.append({
        'Дата': row[col_idx['begin']][:10],
        'Open': float(row[col_idx['open']]),
        'High': float(row[col_idx['high']]),
        'Low': float(row[col_idx['low']]),
        'Close': float(row[col_idx['close']]),
        'Volume': int(row[col_idx['volume']])
    })

df_candles = pd.DataFrame(candle_data)
print(f'✅ Получено {len(df_candles)} свечей')
print(df_candles.to_string())

# ============================================================
# 2. FUTOI (ФИНАЛЬНАЯ РАБОЧАЯ ВЕРСИЯ)
# ============================================================
print(f'\n\n📊 ЗАГРУЗКА ОТКРЫТЫХ ПОЗИЦИЙ (FutOI) {TICKER}')
print('=' * 70)

try:
    futoi_data = api.get_futoi(TICKER, dt_from, dt_till)
    
    if 'futoi' in futoi_data and 'data' in futoi_data['futoi']:
        futoi_columns = futoi_data['futoi']['columns']
        futoi_rows = futoi_data['futoi']['data']
        
        print(f'   Колонки: {futoi_columns}')
        print(f'   Всего записей: {len(futoi_rows)}')
        
        idx = {col: i for i, col in enumerate(futoi_columns)}
        
        # Группируем по дате и типу клиента (FIZ/YUR)
        from collections import defaultdict
        grouped = defaultdict(lambda: {'phys_long': 0, 'phys_short': 0, 'jur_long': 0, 'jur_short': 0})
        
        for row in futoi_rows:
            date = str(row[idx['tradedate']])[:10]
            clgroup = row[idx['clgroup']]
            pos_long = int(row[idx['pos_long']]) if row[idx['pos_long']] else 0
            pos_short = int(row[idx['pos_short']]) if row[idx['pos_short']] else 0
            
            # short хранится с отрицательным знаком — берем модуль
            pos_short = abs(pos_short)
            
            if clgroup == 'FIZ':  # Физические лица
                grouped[date]['phys_long'] += pos_long
                grouped[date]['phys_short'] += pos_short
            elif clgroup == 'YUR':  # Юридические лица
                grouped[date]['jur_long'] += pos_long
                grouped[date]['jur_short'] += pos_short
        
        # Преобразуем в DataFrame
        futoi_list = []
        for date, data in sorted(grouped.items())[-5:]:
            futoi_list.append({
                'Дата': date,
                'Физ.длин.': data['phys_long'],
                'Физ.корот.': data['phys_short'],
                'Юр.длин.': data['jur_long'],
                'Юр.корот.': data['jur_short'],
            })
        
        df_futoi = pd.DataFrame(futoi_list)
        
        print(f'\n📊 ОТКРЫТЫЕ ПОЗИЦИИ ПО ГРУППАМ:')
        print('=' * 80)
        print(df_futoi.to_string(index=True))
        
        # Анализ
        if len(df_futoi) > 0:
            last = df_futoi.iloc[-1]
            
            phys_net = last['Физ.длин.'] - last['Физ.корот.']
            jur_net = last['Юр.длин.'] - last['Юр.корот.']
            
            print(f'\n📈 АНАЛИЗ (последний день, {last["Дата"]}):')
            print(f'   👤 ФИЗИКИ:  +{last["Физ.длин."]:,} / -{last["Физ.корот."]:,} = нетто {phys_net:+,}')
            print(f'   🏢 ЮРИКИ:   +{last["Юр.длин."]:,} / -{last["Юр.корот."]:,} = нетто {jur_net:+,}')
            
            if phys_net > 0 and jur_net < 0:
                print(f'   💡 Физики покупают, юрики продают → ВОЗМОЖЕН РОСТ')
            elif phys_net < 0 and jur_net > 0:
                print(f'   💡 Физики продают, юрики покупают → ВОЗМОЖНО ПАДЕНИЕ')
            else:
                print(f'   💡 Все двигаются в одном направлении')

except Exception as e:
    print(f'❌ Ошибка: {e}')
    import traceback
    traceback.print_exc()



print(f'\n{"=" * 70}')
print(f'✅ ЗАГРУЗКА ЗАВЕРШЕНА')
print(f'   GLDRUBF: {df_candles["Close"].iloc[-1]:.2f} ₽/г')