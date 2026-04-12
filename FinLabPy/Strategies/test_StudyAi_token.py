import os
import sys
from datetime import datetime, timedelta
from MOEXPy.MOEXPy import MOEXPy
def get_sber_candles():
    # 1. Безопасное получение токена
    token = os.environ.get('MOEX_TOKEN')
    if not token:
        print("❌ Ошибка: Переменная окружения MOEX_TOKEN не установлена.")
        sys.exit(1)
    # 2. Инициализация API
    try:
        api = MOEXPy(token=token)
        
        # Конфигурация инструмента
        target_instrument = 'TQBR.SBER'
        timeframe = 'D1'
        days_back = 7
        # Преобразование метаданных
        board, symbol = api.dataname_to_board_symbol(target_instrument)
        moex_tf = api.timeframe_to_moex_timeframe(timeframe)
        # 3. Запрос данных
        start_date = datetime.now() - timedelta(days=days_back)
        end_date = datetime.now()
        
        raw_data = api.get_candles(board, symbol, start_date, end_date, moex_tf)
        # 4. Валидация ответа (MOEX API возвращает вложенные словари)
        if not raw_data or 'candles' not in raw_data or 'data' not in raw_data['candles']:
            print(f"⚠️ Данные по {target_instrument} не получены. Проверьте доступ и тикер.")
            return
        candles = raw_data['candles']['data']
        
        print(f"✅ Успешно! Инструмент: {target_instrument}")
        print(f"✅ Получено свечей: {len(candles)}")
        
        # Вывод последней цены закрытия для проверки
        if candles:
            last_close = candles[-1][4]  # В ответе MOEX [open, close, high, low, value, ...]
            print(f"📌 Последняя цена закрытия: {last_close}")
    except Exception as e:
        print(f"💥 Критическая ошибка при работе с API: {e}")
if __name__ == "__main__":
    get_sber_candles()