"""
MegaAlerts — торговые аномалии MOEX.
Endpoint: https://apim.moex.com/iss/datashop/algopack/{market}/alerts/{ticker}.json
"""

import requests
import os
from datetime import datetime, timedelta


def _get_token():
    return os.getenv('MOEX_TOKEN', '')


# Типы алертов из документации
ALERT_TYPES = {
    'net_vol_99_9_pctl-': '📊 Аном. нетто-объём (продажи)',
    'net_vol_99_9_pctl+': '📊 Аном. нетто-объём (покупки)',
    'vol_99_9_pctl': '📊 Аномальный объём',
    'vol_b_99_9_pctl': '📊 Аном. объём покупок',
    'vol_s_99_9_pctl': '📊 Аном. объём продаж',
    'oi_close_change_99_9_pctl+': '📈 Аном. рост ОИ',
    'oi_close_change_99_9_pctl-': '📉 Аном. падение ОИ',
    'pr_change_99_9_pctl+': '📈 Аном. рост цены',
    'pr_change_99_9_pctl-': '📉 Аном. падение цены',
    'large_trade': '💼 Крупная сделка',
    'volatility_spike': '🌪️ Всплеск волатильности',
}


def get_mega_alerts(ticker, market='eq', days=2, limit=10):
    """
    Получает торговые аномалии для инструмента.
    
    Параметры:
    - ticker: тикер (SBER, CNYRUBF и т.д.)
    - market: eq (акции) или fo (фьючерсы)
    - days: за сколько дней (по умолчанию 2)
    - limit: максимум алертов (по умолчанию 10)
    """
    token = _get_token()
    if not token:
        return []
    
    dt_till = datetime.now()
    dt_from = dt_till - timedelta(days=days)
    
    url = f'https://apim.moex.com/iss/datashop/algopack/{market}/alerts/{ticker}.json'
    
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {token}'
    }
    
    params = {
        'from': dt_from.strftime('%Y-%m-%d'),
        'till': dt_till.strftime('%Y-%m-%d'),
    }
    
    alerts = []
    
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        
        if resp.status_code == 200:
            data = resp.json()
            
            rows = []
            if 'data' in data and 'data' in data['data']:
                rows = data['data']['data']
            elif isinstance(data.get('data'), list):
                rows = data['data']
            
            # Получаем имена колонок
            columns = data['data'].get('columns', [])
            
            # Убираем дубликаты
            seen = set()
            for row in rows:
                # Создаём словарь для удобства
                d = {columns[i]: str(row[i]) for i in range(min(len(columns), len(row)))}
                
                date = d.get('tradedate', '')
                time = d.get('tradetime', '')
                tick = d.get('secid', '')
                alert_type = d.get('alert_type', 'alert')
                
                key = f"{date}|{time}|{tick}|{alert_type}"
                if key in seen:
                    continue
                seen.add(key)
                
                # Человеческое описание типа
                type_desc = ALERT_TYPES.get(alert_type, f'⚠️ {alert_type}')
                
                alerts.append({
                    'time': f"{date} {time}",
                    'type': type_desc,
                    'ticker': tick,
                    'severity': 'high',
                })
        
    except Exception:
        pass
    
    # Последние N
    return alerts[-limit:]
