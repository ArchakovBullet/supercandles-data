"""
Фильтр времени торговых сессий.
Определяет статус ликвидности и даёт рекомендации.
"""

from datetime import datetime, time


def get_session_status():
    """
    Возвращает статус торговой сессии MOEX.
    
    Возвращает:
    - status: CLOSED / OPENING / ACTIVE / LUNCH / CLOSING / EVENING
    - label: текстовая метка
    - liquidity: 0-1 (0 = нет торгов, 1 = высокая ликвидность)
    - warning: предупреждение (если есть)
    """
    now = datetime.now()
    current_time = now.time()
    weekday = now.weekday()  # 0=Пн, 6=Вс
    
    # Выходные
    if weekday >= 5:
        return {
            'status': 'CLOSED',
            'label': '🔴 Выходной',
            'liquidity': 0,
            'warning': 'Рынок закрыт. Данные не обновляются.',
        }
    
    # Основная сессия: 10:00 - 18:45
    opening = time(10, 0)
    opening_end = time(10, 30)
    lunch_start = time(12, 0)
    lunch_end = time(13, 0)
    closing_start = time(18, 30)
    closing_end = time(18, 45)
    evening_end = time(23, 50)
    
    if current_time < opening:
        return {
            'status': 'CLOSED',
            'label': '🔴 Рынок закрыт',
            'liquidity': 0,
            'warning': 'Рынок откроется в 10:00 МСК.',
        }
    elif current_time < opening_end:
        return {
            'status': 'OPENING',
            'label': '🟡 Открытие',
            'liquidity': 0.5,
            'warning': 'Высокая волатильность. Возможны ложные пробои.',
        }
    elif current_time < lunch_start:
        return {
            'status': 'ACTIVE',
            'label': '🟢 Активная сессия',
            'liquidity': 1.0,
            'warning': None,
        }
    elif current_time < lunch_end:
        return {
            'status': 'LUNCH',
            'label': '🔴 Обед',
            'liquidity': 0.3,
            'warning': 'Низкая ликвидность. Сигналы могут быть шумовыми.',
        }
    elif current_time < closing_start:
        return {
            'status': 'ACTIVE',
            'label': '🟢 Активная сессия',
            'liquidity': 1.0,
            'warning': None,
        }
    elif current_time < closing_end:
        return {
            'status': 'CLOSING',
            'label': '🟡 Закрытие',
            'liquidity': 0.5,
            'warning': 'Закрытие позиций. Возможны резкие движения.',
        }
    elif current_time < evening_end:
        return {
            'status': 'EVENING',
            'label': '🔴 Вечерняя сессия',
            'liquidity': 0.3,
            'warning': 'Низкая ликвидность. Широкие спреды.',
        }
    else:
        return {
            'status': 'CLOSED',
            'label': '🔴 Рынок закрыт',
            'liquidity': 0,
            'warning': 'Рынок откроется завтра в 10:00 МСК.',
        }
