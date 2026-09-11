# Переходим в корень проекта
cd E:\Python\FinLabProject

# Создаём папку Brokers (если её нет)
New-Item -Path "FinLabPy\Brokers" -ItemType Directory -Force

# ==================== ФАЙЛ 1: TInvestAPI.py ====================
@"
"""
TInvestAPI.py - Модуль для работы с Т-Инвест API через REST
Автор: Денис
Дата: 12.04.2026
"""

import requests
import urllib3
import os

# Отключаем предупреждения SSL
urllib3.disable_warnings()


class TInvestAPI:
    """Класс для работы с Т-Инвест API"""
    
    def __init__(self, token: str = None):
        """
        Инициализация API
        
        Args:
            token: Токен доступа (если None, берётся из TINVEST_TOKEN)
        """
        self.token = token or os.getenv('TINVEST_TOKEN')
        if not self.token:
            raise ValueError("Токен Т-Инвест не найден!")
        
        self.base_url = "https://invest-public-api.tbank.ru/rest"
        self.headers = {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json'
        }
    
    def get_accounts(self) -> list:
        """
        Получить список счетов пользователя
        
        Returns:
            list: Список счетов
        """
        url = f"{self.base_url}/tinkoff.public.invest.api.contract.v1.UsersService/GetAccounts"
        r = requests.post(url, headers=self.headers, verify=False, json={})
        if r.status_code == 200:
            return r.json().get('accounts', [])
        else:
            print(f" Ошибка получения счетов: {r.status_code}")
            return []
    
    def get_portfolio(self, account_id: str) -> dict:
        """
        Получить портфель по счёту
        
        Args:
            account_id: ID счёта
        
        Returns:
            dict: Информация о портфеле
        """
        url = f"{self.base_url}/tinkoff.public.invest.api.contract.v1.OperationsService/GetPortfolio"
        r = requests.post(url, headers=self.headers, verify=False, 
                         json={'accountId': account_id})
        if r.status_code == 200:
            return r.json()
        else:
            print(f" Ошибка получения портфеля: {r.status_code}")
            return {}
    
    def get_positions(self, account_id: str) -> list:
        """
        Получить позиции по счёту
        
        Args:
            account_id: ID счёта
        
        Returns:
            list: Список позиций
        """
        url = f"{self.base_url}/tinkoff.public.invest.api.contract.v1.OperationsService/GetPositions"
        r = requests.post(url, headers=self.headers, verify=False,
                         json={'accountId': account_id})
        if r.status_code == 200:
            return r.json().get('securities', [])
        else:
            print(f" Ошибка получения позиций: {r.status_code}")
            return []
    
    def place_order(self, account_id: str, figi: str, quantity: int, 
                    direction: str, order_type: str = "MARKET",
                    price: float = None) -> dict:
        """
        Выставить ордер
        
        Args:
            account_id: ID счёта
            figi: Идентификатор инструмента
            quantity: Количество лотов
            direction: "BUY" или "SELL"
            order_type: "MARKET" или "LIMIT"
            price: Цена (для лимитного ордера)
        
        Returns:
            dict: Информация о выставленном ордере
        """
        url = f"{self.base_url}/tinkoff.public.invest.api.contract.v1.OrdersService/PostOrder"
        data = {
            'accountId': account_id,
            'instrumentId': figi,
            'quantity': quantity,
            'direction': direction,
            'orderType': order_type
        }
        if price and order_type == "LIMIT":
            data['price'] = str(price)
        
        r = requests.post(url, headers=self.headers, verify=False, json=data)
        if r.status_code == 200:
            return r.json()
        else:
            print(f" Ошибка выставления ордера: {r.status_code}")
            print(f"   Ответ: {r.text}")
            return {}
    
    def get_order_status(self, account_id: str, order_id: str) -> dict:
        """
        Получить статус ордера
        
        Args:
            account_id: ID счёта
            order_id: ID ордера
        
        Returns:
            dict: Статус ордера
        """
        url = f"{self.base_url}/tinkoff.public.invest.api.contract.v1.OrdersService/GetOrderState"
        r = requests.post(url, headers=self.headers, verify=False,
                         json={'accountId': account_id, 'orderId': order_id})
        if r.status_code == 200:
            return r.json()
        else:
            print(f" Ошибка получения статуса: {r.status_code}")
            return {}
    
    def cancel_order(self, account_id: str, order_id: str) -> bool:
        """
        Отменить ордер
        
        Args:
            account_id: ID счёта
            order_id: ID ордера
        
        Returns:
            bool: True если успешно
        """
        url = f"{self.base_url}/tinkoff.public.invest.api.contract.v1.OrdersService/CancelOrder"
        r = requests.post(url, headers=self.headers, verify=False,
                         json={'accountId': account_id, 'orderId': order_id})
        return r.status_code == 200


# ==================== ТЕСТОВЫЙ ЗАПУСК ====================
if __name__ == '__main__':
    print("=" * 50)
    print("ТЕСТ Т-ИНВЕСТ API")
    print("=" * 50)
    
    try:
        api = TInvestAPI()
        accounts = api.get_accounts()
        print(f" Найдено счетов: {len(accounts)}")
        
        for acc in accounts:
            print(f"   - {acc.get('name')} (ID: {acc.get('id')})")
            
            # Показать портфель для брокерского счёта
            if 'Брокерский' in acc.get('name', ''):
                portfolio = api.get_portfolio(acc['id'])
                if portfolio:
                    total_value = portfolio.get('totalAmountShares', {})
                    print(f"      Стоимость портфеля: {total_value.get('value', 0)} {total_value.get('currency', '')}")
    
    except Exception as e:
        print(f" Ошибка: {e}")
