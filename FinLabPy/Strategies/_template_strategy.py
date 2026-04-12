"""
Название стратегии: [Впиши название]
Автор: [Твоё имя]
Дата: [Дата создания]
Версия: 1.0

Описание:
[Краткое описание логики стратегии]
"""

# ==================== БЛОК ИМПОРТОВ ====================
import backtrader as bt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from MOEXPy.MOEXPy import MOEXPy

import plotly.graph_objects as go
from plotly.subplots import make_subplots


# ==================== БЛОК КОНФИГУРАЦИИ ====================
class StrategyConfig:
    """Конфигурация стратегии"""
    
    TICKER = "SBER"
    BOARD = "TQBR"
    TIMEFRAME = "D1"
    
    FAST_MA = 10
    SLOW_MA = 30
    
    RISK_PER_TRADE = 0.02
    START_CASH = 100000
    
    START_DATE = "2024-01-01"
    END_DATE = "2024-12-31"
    
    COMMISSION = 0.0005


# ==================== БЛОК ЗАГРУЗКИ ДАННЫХ ====================
class DataLoader:
    """Загрузка исторических данных"""
    
    def __init__(self, config: StrategyConfig):
        self.config = config
        self.api = MOEXPy(os.getenv('MOEX_TOKEN'))
    
    def load_from_moex(self) -> pd.DataFrame:
        """Загрузка данных с Московской биржи"""
        board, symbol = self.api.dataname_to_board_symbol(
            f"{self.config.BOARD}.{self.config.TICKER}"
        )
        
        dt_from = datetime.strptime(self.config.START_DATE, "%Y-%m-%d")
        dt_till = datetime.strptime(self.config.END_DATE, "%Y-%m-%d")
        moex_tf = self.api.timeframe_to_moex_timeframe(self.config.TIMEFRAME)
        
        candles = self.api.get_candles(board, symbol, dt_from, dt_till, moex_tf)
        
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
    """Основной класс стратегии для BackTrader"""
    
    params = (
        ('fast_ma', 10),
        ('slow_ma', 30),
        ('risk_per_trade', 0.02),
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
    
    # ==================== БЛОК ВХОДА В ПОЗИЦИЮ ====================
    def next(self):
        """Вызывается на каждом баре"""
        
        if self.order:
            return
        
        if not self.position:
            # ====== СИГНАЛ НА ПОКУПКУ ======
            if self.crossover > 0:
                size = self.calculate_position_size()
                self.order = self.buy(size=size)
                self.log(f'BUY SIGNAL | Price: {self.data.close[0]:.2f}')
        
        else:
            # ====== СИГНАЛ НА ПРОДАЖУ ======
            if self.crossover < 0:
                self.order = self.sell(size=self.position.size)
                self.log(f'SELL SIGNAL | Price: {self.data.close[0]:.2f}')
    
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
                self.log(f'BUY EXECUTED | Price: {order.executed.price:.2f}')
            else:
                self.log(f'SELL EXECUTED | Price: {order.executed.price:.2f}')
        
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log(f'ORDER FAILED | Status: {order.getstatusname()}')
        
        self.order = None
    
    def notify_trade(self, trade):
        """Вызывается при закрытии сделки"""
        if trade.isclosed:
            self.trades.append({
                'entry_date': trade.open_datetime(),
                'exit_date': trade.close_datetime(),
                'pnl': trade.pnl,
                'pnl_comm': trade.pnlcomm,
            })
            self.log(f'TRADE CLOSED | PnL: {trade.pnl:.2f} | Net: {trade.pnlcomm:.2f}')
    
    # ==================== БЛОК ЛОГИРОВАНИЯ ====================
    def log(self, txt: str):
        """Логирование с временной меткой"""
        dt = self.datas[0].datetime.date(0)
        print(f'{dt.isoformat()} | {txt}')
    
    # ==================== БЛОК ВЫХОДА ИЗ ПОЗИЦИИ ====================
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


# ==================== БЛОК ЗАПУСКА ТЕСТИРОВАНИЯ ====================
class BacktestEngine:
    """Движок для запуска бэктестов"""
    
    def __init__(self, config: StrategyConfig):
        self.config = config
        self.cerebro = bt.Cerebro()
    
    def setup(self, data: pd.DataFrame):
        """Настройка Cerebro"""
        data_feed = bt.feeds.PandasData(dataname=data)
        self.cerebro.adddata(data_feed)
        
        self.cerebro.addstrategy(
            TradingStrategy,
            fast_ma=self.config.FAST_MA,
            slow_ma=self.config.SLOW_MA,
            risk_per_trade=self.config.RISK_PER_TRADE
        )
        
        self.cerebro.broker.setcash(self.config.START_CASH)
        self.cerebro.broker.setcommission(commission=self.config.COMMISSION)
        
        self.cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
        self.cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
        self.cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
    
    def run(self):
        """Запуск тестирования"""
        print('=' * 50)
        print('STARTING BACKTEST')
        print(f'Initial Portfolio: {self.cerebro.broker.getvalue():.2f}')
        print('=' * 50)
        
        results = self.cerebro.run()
        
        print('=' * 50)
        print(f'Final Portfolio: {self.cerebro.broker.getvalue():.2f}')
        print('=' * 50)
        
        return results


# ==================== БЛОК ВИЗУАЛИЗАЦИИ ====================
class Visualizer:
    """Визуализация результатов"""
    
    @staticmethod
    def plot_candles_with_signals(df: pd.DataFrame, trades: list, title: str = "Trading Signals"):
        """Построение графика со сделками"""
        
        fig = make_subplots(
            rows=2, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.05,
            row_heights=[0.7, 0.3]
        )
        
        fig.add_trace(
            go.Candlestick(
                x=df.index,
                open=df['open'],
                high=df['high'],
                low=df['low'],
                close=df['close'],
                name='Price'
            ),
            row=1, col=1
        )
        
        for trade in trades:
            color = 'green' if trade['pnl'] > 0 else 'red'
            symbol = 'triangle-up' if trade['pnl'] > 0 else 'triangle-down'
            
            fig.add_trace(
                go.Scatter(
                    x=[trade['entry_date']],
                    y=[trade['entry_price']],
                    mode='markers',
                    marker=dict(size=10, color=color, symbol=symbol),
                    name=f"{'Win' if trade['pnl'] > 0 else 'Loss'}"
                ),
                row=1, col=1
            )
        
        colors = ['green' if df['close'].iloc[i] >= df['open'].iloc[i] else 'red' 
                  for i in range(len(df))]
        fig.add_trace(
            go.Bar(x=df.index, y=df['volume'], name='Volume', marker_color=colors),
            row=2, col=1
        )
        
        fig.update_layout(
            title=title,
            template='plotly_dark',
            height=800
        )
        
        fig.show()


# ==================== БЛОК ЗАПУСКА (MAIN) ====================
def main():
    """Главная функция запуска"""
    
    print("=" * 60)
    print("ЗАПУСК СТРАТЕГИИ")
    print("=" * 60)
    
    config = StrategyConfig()
    loader = DataLoader(config)
    
    try:
        df = loader.load_from_moex()
        print(f"✅ Данные загружены с MOEX: {len(df)} баров")
    except Exception as e:
        print(f"❌ Ошибка загрузки: {e}")
        return
    
    engine = BacktestEngine(config)
    engine.setup(df)
    results = engine.run()
    
    strat = results[0]
    if strat.trades:
        Visualizer.plot_candles_with_signals(df, strat.trades, 
            f"{config.TICKER} - {config.TIMEFRAME}")


# ==================== ТОЧКА ВХОДА ====================
if __name__ == "__main__":
    main()