"""
Название стратегии: [Впиши название]
Автор: Денис
Дата: 12.04.2026
Версия: 1.0

Описание:
[Краткое описание логики стратегии]

Особенности:
- Интегрированы Т-Инвест и АЛОР для реальной торговли
- Бумажные сделки в BackTrader + опциональные реальные ордера
"""

# ==================== БЛОК ИМПОРТОВ ====================
import backtrader as bt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
import sys

# Добавляем путь к проекту
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from MOEXPy.MOEXPy import MOEXPy
from Brokers.TInvestAPI import TInvestAPI
from Brokers.AlorAPI import AlorAPI

import plotly.graph_objects as go
from plotly.subplots import make_subplots


# ==================== БЛОК КОНФИГУРАЦИИ ====================
class StrategyConfig:
    """Конфигурация стратегии"""
    
    # Инструмент и таймфрейм
    TICKER = "SBER"
    BOARD = "TQBR"
    TIMEFRAME = "D1"
    
    # Параметры стратегии
    FAST_MA = 10
    SLOW_MA = 30
    
    # Управление капиталом
    RISK_PER_TRADE = 0.02
    START_CASH = 100000
    
    # Даты тестирования
    START_DATE = "2024-01-01"
    END_DATE = "2024-12-31"
    
    # Комиссия
    COMMISSION = 0.0005
    
    # Режим реальной торговли
    LIVE_TRADING = False  # True - отправлять ордера брокерам
    BROKER = "TINVEST"    # "TINVEST" или "ALOR"
    
    # Настройки брокеров
    TINVEST_ACCOUNT_ID = "2178952467"  # Брокерский счёт
    TINVEST_FIGI_SBER = "BBG004730N88"  # FIGI для SBER


# ==================== БЛОК ЗАГРУЗКИ ДАННЫХ ====================
def load_data(config: StrategyConfig) -> pd.DataFrame:
    """Загрузка исторических данных"""
    
    token = os.getenv('MOEX_TOKEN')
    if not token:
        token_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '..', 'moex_token.txt')
        if os.path.exists(token_path):
            with open(token_path, 'r') as f:
                token = f.read().strip()
    
    api = MOEXPy(token)
    board, symbol = api.dataname_to_board_symbol(f"{config.BOARD}.{config.TICKER}")
    
    dt_from = datetime.strptime(config.START_DATE, "%Y-%m-%d")
    dt_till = datetime.strptime(config.END_DATE, "%Y-%m-%d")
    moex_tf = api.timeframe_to_moex_timeframe(config.TIMEFRAME)
    
    candles = api.get_candles(board, symbol, dt_from, dt_till, moex_tf)
    
    col_idx = {col: idx for idx, col in enumerate(candles['candles']['columns'])}
    df = pd.DataFrame([{
        'datetime': row[col_idx['begin']],
        'open': float(row[col_idx['open']]),
        'high': float(row[col_idx['high']]),
        'low': float(row[col_idx['low']]),
        'close': float(row[col_idx['close']]),
        'volume': float(row[col_idx['volume']])
    } for row in candles['candles']['data']])
    
    df['datetime'] = pd.to_datetime(df['datetime'])
    df.set_index('datetime', inplace=True)
    
    return df


# ==================== БЛОК СТРАТЕГИИ (BACKTRADER) ====================
class TradingStrategy(bt.Strategy):
    """Основной класс стратегии с поддержкой реальных брокеров"""
    
    params = (
        ('fast_ma', 10),
        ('slow_ma', 30),
        ('risk_per_trade', 0.02),
        ('live_trading', False),
        ('broker', 'TINVEST'),
    )
    
    def __init__(self):
        """Инициализация стратегии"""
        # ========== ИНИЦИАЛИЗАЦИЯ ==========
        self.order = None
        self.trades = []
        
        # Индикаторы
        self.fast_ma = bt.indicators.SMA(self.data.close, period=self.params.fast_ma)
        self.slow_ma = bt.indicators.SMA(self.data.close, period=self.params.slow_ma)
        self.crossover = bt.indicators.CrossOver(self.fast_ma, self.slow_ma)
        
        # Инициализация брокеров (если включена живая торговля)
        if self.params.live_trading:
            self.init_brokers()
    
    def init_brokers(self):
        """Инициализация API брокеров"""
        try:
            if self.params.broker == "TINVEST":
                self.broker_api = TInvestAPI()
                self.account_id = StrategyConfig.TINVEST_ACCOUNT_ID
                self.figi = StrategyConfig.TINVEST_FIGI_SBER
                self.log(" Т-Инвест API инициализирован")
            elif self.params.broker == "ALOR":
                self.broker_api = AlorAPI()
                self.log(" АЛОР API инициализирован")
        except Exception as e:
            self.log(f" Ошибка инициализации брокера: {e}")
            self.params.live_trading = False
    
    # ==================== БЛОК ВХОДА В ПОЗИЦИЮ ====================
    def next(self):
        """Вызывается на каждом баре"""
        
        if self.order:
            return
        
        if not self.position:
            # ====== СИГНАЛ НА ПОКУПКУ ======
            if self.crossover > 0:
                size = self.calculate_position_size()
                
                # Бумажная сделка в BackTrader
                self.order = self.buy(size=size)
                self.log(f'BUY SIGNAL | Price: {self.data.close[0]:.2f}')
                
                # Реальный ордер брокеру
                if self.params.live_trading:
                    self.place_real_order("BUY", size, self.data.close[0])
        
        else:
            # ====== СИГНАЛ НА ПРОДАЖУ ======
            if self.crossover < 0:
                # Бумажная сделка в BackTrader
                self.order = self.sell(size=self.position.size)
                self.log(f'SELL SIGNAL | Price: {self.data.close[0]:.2f}')
                
                # Реальный ордер брокеру
                if self.params.live_trading:
                    self.place_real_order("SELL", self.position.size, self.data.close[0])
    
    def place_real_order(self, direction: str, size: int, price: float):
        """Отправка реального ордера брокеру"""
        try:
            if self.params.broker == "TINVEST":
                result = self.broker_api.place_order(
                    account_id=self.account_id,
                    figi=self.figi,
                    quantity=size,
                    direction=direction,
                    order_type="MARKET"
                )
                if result:
                    self.log(f" Реальный ордер {direction} отправлен в Т-Инвест")
                    
            elif self.params.broker == "ALOR":
                side = "buy" if direction == "BUY" else "sell"
                result = self.broker_api.place_order(
                    symbol=StrategyConfig.TICKER,
                    side=side,
                    quantity=size
                )
                if result:
                    self.log(f" Реальный ордер {side} отправлен в АЛОР")
                    
        except Exception as e:
            self.log(f" Ошибка отправки реального ордера: {e}")
    
    # ==================== БЛОК УПРАВЛЕНИЯ РИСКАМИ ====================
    def calculate_position_size(self) -> int:
        """Расчёт размера позиции"""
        cash = self.broker.get_cash()
        price = self.data.close[0]
        risk_amount = cash * self.params.risk_per_trade
        size = int(risk_amount / price)
        return max(1, size)
    
    # ==================== БЛОК ОБРАБОТКИ ОРДЕРОВ ====================
    def notify_order(self, order):
        """Вызывается при изменении статуса ордера"""
        
        if order.status in [order.Submitted, order.Accepted]:
            return
        
        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(f'BUY EXECUTED | Price: {order.executed.price:.2f} | Size: {order.executed.size}')
            else:
                self.log(f'SELL EXECUTED | Price: {order.executed.price:.2f} | Size: {order.executed.size}')
        
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log(f'ORDER FAILED | Status: {order.getstatusname()}')
        
        self.order = None
    
    def notify_trade(self, trade):
        """Вызывается при закрытии сделки"""
        if trade.isclosed:
            self.trades.append({
                'entry_date': trade.open_datetime(),
                'exit_date': trade.close_datetime(),
                'entry_price': trade.price,
                'pnl': trade.pnl,
                'pnl_comm': trade.pnlcomm,
            })
            self.log(f'TRADE CLOSED | PnL: {trade.pnl:.2f} | Net: {trade.pnlcomm:.2f}')
    
    # ==================== БЛОК ЛОГИРОВАНИЯ ====================
    def log(self, txt: str):
        """Логирование с временной меткой"""
        dt = self.datas[0].datetime.date(0)
        print(f'{dt.isoformat()} | {txt}')
    
    # ==================== БЛОК ЗАВЕРШЕНИЯ ====================
    def stop(self):
        """Вызывается в конце тестирования"""
        self.log('=' * 50)
        self.log('STRATEGY FINISHED')
        self.log(f'Final Portfolio Value: {self.broker.getvalue():.2f}')
        
        if self.trades:
            trades_df = pd.DataFrame(self.trades)
            winning_trades = trades_df[trades_df['pnl'] > 0]
            self.log(f'Total Trades: {len(self.trades)}')
            if len(self.trades) > 0:
                self.log(f'Win Rate: {len(winning_trades)/len(self.trades)*100:.1f}%')


# ==================== БЛОК ЗАПУСКА ====================
def main():
    """Главная функция запуска"""
    
    print("=" * 60)
    print("ЗАПУСК СТРАТЕГИИ С ПОДДЕРЖКОЙ БРОКЕРОВ")
    print("=" * 60)
    
    config = StrategyConfig()
    
    # Выбор режима
    print(f"\nРежим реальной торговли: {' ВКЛЮЧЕН' if config.LIVE_TRADING else ' ВЫКЛЮЧЕН (бумажный)'}")
    if config.LIVE_TRADING:
        print(f"Брокер: {config.BROKER}")
    
    # Загрузка данных
    print("\nЗагрузка данных...")
    df = load_data(config)
    print(f" Загружено {len(df)} баров")
    
    # Настройка Cerebro
    cerebro = bt.Cerebro()
    cerebro.addstrategy(
        TradingStrategy,
        fast_ma=config.FAST_MA,
        slow_ma=config.SLOW_MA,
        risk_per_trade=config.RISK_PER_TRADE,
        live_trading=config.LIVE_TRADING,
        broker=config.BROKER
    )
    
    data_feed = bt.feeds.PandasData(dataname=df)
    cerebro.adddata(data_feed)
    
    cerebro.broker.setcash(config.START_CASH)
    cerebro.broker.setcommission(commission=config.COMMISSION)
    
    print(f"\nНачальный капитал: {cerebro.broker.getvalue():.2f}")
    
    # Запуск
    cerebro.run()
    
    print(f"Конечный капитал: {cerebro.broker.getvalue():.2f}")
    print(f"Доходность: {(cerebro.broker.getvalue() / config.START_CASH - 1) * 100:.2f}%")


if __name__ == "__main__":
    main()
