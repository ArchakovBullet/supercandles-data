from MOEXPy.MOEXPy import MOEXPy
from datetime import datetime, timedelta

# Читаем токен из файла
with open('moex_token.txt', 'r') as f:
    token = f.read().strip()

print('🔑 Инициализация MOEXPy с токеном...')
api = MOEXPy(token=token)

# Получаем свечи Сбербанка
board, symbol = api.dataname_to_board_symbol('TQBR.SBER')
moex_tf = api.timeframe_to_moex_timeframe('D1')
candles = api.get_candles(board, symbol, datetime.now() - timedelta(days=7), datetime.now(), moex_tf)

print(f'✅ Получено {len(candles["candles"]["data"])} свечей')
print('   Algopack работает на локальном ПК')