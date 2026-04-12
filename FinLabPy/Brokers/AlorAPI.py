"""
AlorAPI.py - Модуль для работы с АЛОР API через REST
Автор: Денис
Дата: 12.04.2026
"""

import requests
import os
from datetime import datetime


class AlorAPI:
    """Класс для работы с АЛОР API"""
    
    def __init__(self, refresh_token: str = None):
        """
        Инициализация API
        
        Args:
            refresh_token: Refresh токен (если None, берётся из ALOR_TOKEN)
        """
        self.refresh_token = refresh_token or os.getenv('ALOR_TOKEN')
        if not self.refresh_token:
            raise ValueError("Токен АЛОР не найден!")
        
        self.access_token = None
        self.base_url = "https://api.alor.ru"
        self._refresh_access_token()
    
    def _refresh_access_token(self) -> bool:
        """
        Обновить access token
        
        Returns:
            bool: True если успешно
        """
        url = "https://oauth.alor.ru/refresh"
        r = requests.post(url, json={'token': self.refresh_token})
        if r.status_code == 200:
            self.access_token = r.json().get('AccessToken')
            return True
        else:
            print(f" Ошибка получения access token: {r.status_code}")
            return False
    
    def get_headers(self) -> dict:
        """
        Получить заголовки с авторизацией
        
        Returns:
            dict: Заголовки
        """
        if not self.access_token:
            self._refresh_access_token()
        return {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }
    
    def get_security_info(self, symbol: str, exchange: str = "MOEX") -> dict:
        """
        Получить информацию по инструменту
        
        Args:
            symbol: Тикер (например, "SBER")
            exchange: Биржа ("MOEX" по умолчанию)
        
        Returns:
            dict: Информация об инструменте
        """
        url = f"{self.base_url}/md/v2/securities/{exchange}/{symbol}"
        r = requests.get(url, headers=self.get_headers())
        if r.status_code == 200:
            return r.json()
        else:
            print(f" Ошибка получения данных по {symbol}: {r.status_code}")
            return {}
    
    def get_orderbook(self, symbol: str, exchange: str = "MOEX", depth: int = 20) -> dict:
        """
        Получить стакан заявок
        
        Args:
            symbol: Тикер
            exchange: Биржа
            depth: Глубина стакана
        
        Returns:
            dict: Стакан заявок
        """
        url = f"{self.base_url}/md/v2/orderbooks/{exchange}/{symbol}"
        params = {'depth': depth}
        r = requests.get(url, headers=self.get_headers(), params=params)
        if r.status_code == 200:
            return r.json()
        else:
            print(f" Ошибка получения стакана: {r.status_code}")
            return {}
    
    def get_portfolio(self) -> dict:
        """
        Получить портфель
        
        Returns:
            dict: Информация о портфеле
        """
        url = f"{self.base_url}/client/v1.0/portfolio"
        r = requests.get(url, headers=self.get_headers())
        if r.status_code == 200:
            return r.json()
        else:
            print(f" Ошибка получения портфеля: {r.status_code}")
            return {}
    
    def get_positions(self) -> list:
        """
        Получить позиции
        
        Returns:
            list: Список позиций
        """
        url = f"{self.base_url}/client/v1.0/positions"
        r = requests.get(url, headers=self.get_headers())
        if r.status_code == 200:
            return r.json().get('positions', [])
        else:
            print(f" Ошибка получения позиций: {r.status_code}")
            return []
    
    def place_order(self, symbol: str, side: str, quantity: int,
                    price: float = None, exchange: str = "MOEX") -> dict:
        """
        Выставить ордер
        
        Args:
            symbol: Тикер
            side: "buy" или "sell"
            quantity: Количество лотов
            price: Цена (если None  рыночный ордер)
            exchange: Биржа
        
        Returns:
            dict: Информация об ордере
        """
        url = f"{self.base_url}/commandapi/warptrans/1.0/orders"
        data = {
            'symbol': symbol,
            'side': side,
            'quantity': quantity,
            'exchange': exchange
        }
        if price:
            data['type'] = 'limit'
            data['price'] = price
        else:
            data['type'] = 'market'
        
        r = requests.post(url, headers=self.get_headers(), json=data)
        if r.status_code == 200:
            return r.json()
        else:
            print(f" Ошибка выставления ордера: {r.status_code}")
            print(f"   Ответ: {r.text}")
            return {}
    
    def cancel_order(self, order_id: str, exchange: str = "MOEX") -> bool:
        """
        Отменить ордер
        
        Args:
            order_id: ID ордера
            exchange: Биржа
        
        Returns:
            bool: True если успешно
        """
        url = f"{self.base_url}/commandapi/warptrans/1.0/orders/{order_id}"
        params = {'exchange': exchange}
        r = requests.delete(url, headers=self.get_headers(), params=params)
        return r.status_code == 200
    
    def get_orders(self) -> list:
        """
        Получить список активных ордеров
        
        Returns:
            list: Список ордеров
        """
        url = f"{self.base_url}/commandapi/warptrans/1.0/orders"
        r = requests.get(url, headers=self.get_headers())
        if r.status_code == 200:
            return r.json()
        else:
            print(f" Ошибка получения ордеров: {r.status_code}")
            return []


# ==================== ТЕСТОВЫЙ ЗАПУСК ====================
if __name__ == '__main__':
    print("=" * 50)
    print("ТЕСТ АЛОР API")
    print("=" * 50)
    
    try:
        api = AlorAPI()
        print(" Access token получен")
        
        # Проверить информацию по SBER
        info = api.get_security_info("SBER")
        if info:
            print(f"   SBER: bid={info.get('bid')}, ask={info.get('ask')}")
            print(f"   Время: {datetime.now().strftime('%H:%M:%S')}")
            if not info.get('bid'):
                print("   (Биржа закрыта  это нормально)")
        
        # Проверить портфель
        portfolio = api.get_portfolio()
        if portfolio:
            print(f"   Портфель: {portfolio.get('portfolioValue', 0)} RUB")
    
    except Exception as e:
        print(f" Ошибка: {e}")
