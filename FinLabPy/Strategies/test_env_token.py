import os
from MOEXPy.MOEXPy import MOEXPy
from datetime import datetime, timedelta

# Читаем токен из переменной окружения
token = os.environ.get('MOEX_TOKEN')
if not token:
    print("❌ Токен не найден в переменной окружения")
    exit()

print('🔑 Инициализация MOEXPy с токеном из переменной окружения...')
api = MOEXPy(token=token)

# Получаем свечи Сбербанка
board, symbol = api.dataname_to_board_symbol('TQBR.SBER')
moex_tf = api.timeframe_to_moex_timeframe('D1')
candles = api.get_candles(board, symbol, datetime.now() - timedelta(days=7), datetime.now(), moex_tf)

print(f'✅ Получено {len(candles["candles"]["data"])} свечей')
print('   Algopack работает через переменную окружения')