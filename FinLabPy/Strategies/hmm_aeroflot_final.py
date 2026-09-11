"""
HMM Стратегия для Аэрофлота: ATR-стоп + трейлинг в безубыток.
Строит график с индикаторами и точками входа/выхода.

Использование:
    python FinLabPy/Strategies/hmm_aeroflot_final.py
"""
import os
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent if '__file__' in dir() else Path('.').absolute()
sys.path.insert(0, str(project_root))

import numpy as np
import polars as pl
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from hmmlearn import hmm as hmmlearn_hmm
import talib

from FinLabPy.DataCollectors.osengine_loader import OsEngineLoader
from FinLabPy.My_Indicators.technical_features import add_technical_features
from FinLabPy.Utils import setup_logger

logger = setup_logger('hmm_aeroflot')


def prepare_features(df: pl.DataFrame) -> tuple:
    """Подготавливает признаки, удаляет NaN/Inf."""
    df = add_technical_features(df)
    
    features = [
        'returns', 'volatility', 'volume_ratio', 'trend_strength',
        'price_vs_sma20', 'price_vs_sma50', 'rsi', 'macd_hist', 'bb_position'
    ]
    
    X = df.select(features).to_numpy().astype(np.float64)
    y = df['future_returns_1d'].to_numpy().astype(np.float64)
    close = df['close'].to_numpy().astype(np.float64)
    high = df['high'].to_numpy().astype(np.float64)
    low = df['low'].to_numpy().astype(np.float64)
    dates = df['date'].to_list()
    
    mask = ~np.isnan(X).any(axis=1) & ~np.isinf(X).any(axis=1)
    mask &= ~np.isnan(y) & ~np.isinf(y)
    
    X = X[mask]
    y = y[mask]
    close = close[mask]
    high = high[mask]
    low = low[mask]
    dates = [d for i, d in enumerate(dates) if mask[i]]
    
    return X, y, close, high, low, dates


def train_hmm(X: np.ndarray, n_states: int = 4) -> hmmlearn_hmm.GaussianHMM:
    """Обучает HMM."""
    model = hmmlearn_hmm.GaussianHMM(
        n_components=n_states,
        covariance_type='full',
        n_iter=1000,
        random_state=42,
        tol=1e-4,
    )
    model.fit(X)
    return model


def compute_super_trend(high: np.ndarray, low: np.ndarray, close: np.ndarray, 
                         period: int = 10, multiplier: float = 3.0) -> tuple:
    """
    Вычисляет индикатор SuperTrend.
    Возвращает: (supertrend_line, direction)
        direction: +1 = UP (зелёный), -1 = DOWN (красный)
    """
    atr = talib.ATR(high, low, close, timeperiod=period)
    
    # Базовые линии
    hl_avg = (high + low) / 2
    
    upper_band = hl_avg + multiplier * atr
    lower_band = hl_avg - multiplier * atr
    
    supertrend = np.zeros(len(close))
    direction = np.zeros(len(close))
    
    for i in range(1, len(close)):
        # Верхняя полоса
        if upper_band[i] < upper_band[i-1] or close[i-1] > upper_band[i-1]:
            upper_band[i] = upper_band[i]
        else:
            upper_band[i] = upper_band[i-1]
        
        # Нижняя полоса
        if lower_band[i] > lower_band[i-1] or close[i-1] < lower_band[i-1]:
            lower_band[i] = lower_band[i]
        else:
            lower_band[i] = lower_band[i-1]
        
        # Направление
        if close[i] > upper_band[i-1]:
            direction[i] = 1  # UP
            supertrend[i] = lower_band[i]
        elif close[i] < lower_band[i-1]:
            direction[i] = -1  # DOWN
            supertrend[i] = upper_band[i]
        else:
            direction[i] = direction[i-1]
            supertrend[i] = lower_band[i] if direction[i] == 1 else upper_band[i]
    
    return supertrend, direction


def backtest_with_atr_stop(model, X: np.ndarray, close: np.ndarray, 
                           high: np.ndarray, low: np.ndarray,
                           up_state: int, atr_mult: float = 2.0, 
                           breakeven_pct: float = 3.0) -> dict:
    """
    HMM стратегия с ATR-стопом и трейлингом в безубыток.
    
    - Вход: HMM в UP-режиме
    - Начальный стоп: entry_price - atr_mult * ATR(14)
    - Трейлинг: если прибыль > breakeven_pct → стоп = цена входа (безубыток)
    - Выход: по стопу, по обратному сигналу HMM, или в конце данных
    """
    states = model.predict(X)
    atr = talib.ATR(high, low, close, timeperiod=14)
    
    n = len(close)
    
    position = 0
    entry_price = 0
    entry_bar = 0
    stop_level = 0
    
    trades = []
    equity = np.ones(n)
    max_dd = 0
    peak = 1.0
    
    signal_exits = 0
    stop_exits = 0
    end_exits = 0
    
    # Для логирования на каждом баре
    positions_plot = np.zeros(n)  # 1 = в позиции, 0 = нет
    stop_levels_plot = np.full(n, np.nan)  # уровень стопа
    
    for i in range(1, n):
        equity[i] = equity[i-1]
        
        # Если в позиции — проверяем стоп
        if position == 1:
            current_return = (close[i] - entry_price) / entry_price * 100
            
            # Обновляем стоп (трейлинг в безубыток)
            if current_return >= breakeven_pct:
                stop_level = max(stop_level, entry_price)
            
            stop_levels_plot[i] = stop_level
            
            # Проверка срабатывания стопа
            if low[i] <= stop_level:
                # Стоп сработал
                exit_price = stop_level
                ret = (exit_price - entry_price) / entry_price
                equity[i] = equity[i-1] * (1 + ret)
                position = 0
                stop_exits += 1
                trades.append({
                    'type': 'STOP', 'bar': i, 'price': exit_price, 
                    'return': ret, 'bars_held': i - entry_bar,
                })
                stop_levels_plot[i] = np.nan
                continue
        
        # Сигнал HMM
        if states[i] == up_state and position == 0:
            # Вход
            position = 1
            entry_price = close[i]
            entry_bar = i
            stop_level = entry_price - atr_mult * atr[i]
            positions_plot[i] = 1
            stop_levels_plot[i] = stop_level
            trades.append({'type': 'BUY', 'bar': i, 'price': close[i]})
        
        elif states[i] != up_state and position == 1:
            # Выход по обратному сигналу
            ret = (close[i] - entry_price) / entry_price
            equity[i] = equity[i-1] * (1 + ret)
            position = 0
            signal_exits += 1
            stop_levels_plot[i] = np.nan
            trades.append({
                'type': 'SIGNAL', 'bar': i, 'price': close[i],
                'return': ret, 'bars_held': i - entry_bar,
            })
        
        if position == 1:
            positions_plot[i] = 1
        
        # Просадка
        if equity[i] > peak:
            peak = equity[i]
        dd = (equity[i] - peak) / peak
        if dd < max_dd:
            max_dd = dd
    
    # Закрытие в конце
    if position == 1:
        ret = (close[-1] - entry_price) / entry_price
        equity[-1] = equity[-2] * (1 + ret)
        end_exits += 1
        trades.append({
            'type': 'END', 'bar': n-1, 'price': close[-1],
            'return': ret, 'bars_held': n - 1 - entry_bar,
        })
    
    total_ret = float((equity[-1] - 1) * 100)
    bh_ret = float((close[-1] - close[0]) / close[0] * 100)
    
    completed = [t for t in trades if 'return' in t]
    wins = [t for t in completed if t['return'] > 0]
    
    return {
        'total_return': total_ret,
        'bh_return': bh_ret,
        'delta': total_ret - bh_ret,
        'trades_total': len(trades),
        'completed': len(completed),
        'win_rate': len(wins) / max(len(completed), 1) * 100,
        'max_dd': float(max_dd * 100),
        'signal_exits': signal_exits,
        'stop_exits': stop_exits,
        'end_exits': end_exits,
        'avg_bars': float(np.mean([t['bars_held'] for t in completed])) if completed else 0,
        'avg_return': float(np.mean([t['return'] for t in completed]) * 100) if completed else 0,
        # Для графика
        'equity': equity,
        'states': states,
        'positions': positions_plot,
        'stop_levels': stop_levels_plot,
        'close': close,
        'high': high,
        'low': low,
        'dates': [],
        'trades': trades,
    }


def plot_results(results: dict, ticker: str, dates: list):
    """Строит график с ценой, HMM-режимами, SuperTrend, ATR-стопом, вход/выход."""
    states = results['states']
    close = results['close']
    high = results['high']
    low = results['low']
    equity = results['equity']
    positions = results['positions']
    stop_levels = results['stop_levels']
    trades = results['trades']
    
    # SuperTrend
    st_line, st_dir = compute_super_trend(high, low, close, period=10, multiplier=3.0)
    
    n = len(close)
    x = np.arange(n)
    
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(18, 10), gridspec_kw={'height_ratios': [3, 1]})
    
    # ---- ГРАФИК 1: Цена + режимы + входы/выходы ----
    
    # Цветной фон по режимам HMM
    colors_regime = ['#FFE0E0', '#E0FFE0', '#E0E0FF', '#FFFFE0']  # красный, зелёный, синий, жёлтый
    unique_states = sorted(set(states))
    regime_names = {s: f'State {s}' for s in unique_states}
    
    # Находим UP-режим (максимум avg return мы не знаем здесь, просто раскрашиваем)
    for state in unique_states:
        mask = states == state
        if mask.sum() < 3:
            continue
        
        # Находим непрерывные сегменты
        segments = []
        start = None
        for i in range(n):
            if mask[i] and start is None:
                start = i
            elif not mask[i] and start is not None:
                segments.append((start, i-1))
                start = None
        if start is not None:
            segments.append((start, n-1))
        
        color = colors_regime[state % len(colors_regime)]
        for s, e in segments:
            if e > s:
                ax1.axvspan(s, e, alpha=0.2, color=color)
    
    # Цена
    ax1.plot(x, close, 'k-', linewidth=1.2, label=f'{ticker} Close', zorder=5)
    
    # SuperTrend
    ax1.plot(x, st_line, 'b--', linewidth=1, alpha=0.7, label='SuperTrend (10,3)')
    
    # Точки входа/выхода
    buys = [t for t in trades if t['type'] == 'BUY']
    exits = [t for t in trades if t['type'] in ('SIGNAL', 'STOP', 'END')]
    
    if buys:
        bx = [t['bar'] for t in buys]
        bp = [t['price'] for t in buys]
        ax1.scatter(bx, bp, c='green', marker='^', s=120, zorder=10, 
                   edgecolors='darkgreen', linewidth=1.5, label='BUY (HMM UP)')
    
    if exits:
        # Разные цвета для разных типов выхода
        signal_x = [t['bar'] for t in exits if t['type'] == 'SIGNAL']
        signal_p = [t['price'] for t in exits if t['type'] == 'SIGNAL']
        stop_x = [t['bar'] for t in exits if t['type'] == 'STOP']
        stop_p = [t['price'] for t in exits if t['type'] == 'STOP']
        end_x = [t['bar'] for t in exits if t['type'] == 'END']
        end_p = [t['price'] for t in exits if t['type'] == 'END']
        
        if signal_x:
            ax1.scatter(signal_x, signal_p, c='blue', marker='v', s=120, zorder=10,
                       edgecolors='darkblue', linewidth=1.5, label='SELL (HMM сигнал)')
        if stop_x:
            ax1.scatter(stop_x, stop_p, c='red', marker='v', s=120, zorder=10,
                       edgecolors='darkred', linewidth=1.5, label='SELL (ATR-стоп)')
        if end_x:
            ax1.scatter(end_x, end_p, c='gray', marker='v', s=100, zorder=10,
                       edgecolors='black', linewidth=1.5, label='SELL (конец)')
    
    ax1.set_ylabel('Цена (₽)')
    ax1.set_title(f'HMM Стратегия: {ticker} | ATR-стоп 2×ATR | Трейлинг-безубыток 3%', 
                  fontsize=13, fontweight='bold')
    ax1.legend(loc='upper left', fontsize=9)
    ax1.grid(True, alpha=0.3)
    
    # ---- ГРАФИК 2: Эквити ----
    ax2.plot(x, equity, 'g-', linewidth=1.5, label='Equity (HMM)')
    ax2.axhline(y=1.0, color='gray', linestyle='--', alpha=0.5, label='Начальный капитал')
    
    # Buy & Hold
    bh = (close - close[0]) / close[0] + 1
    ax2.plot(x, bh, 'k--', linewidth=1, alpha=0.5, label='Buy & Hold')
    
    ax2.set_xlabel('Бары (дни)')
    ax2.set_ylabel('Капитал (× начального)')
    ax2.legend(loc='upper left', fontsize=9)
    ax2.grid(True, alpha=0.3)
    
    # Итоговая статистика на графике
    text = (
        f'HMM: {results["total_return"]:.1f}% | B&H: {results["bh_return"]:.1f}% | Δ: {results["delta"]:.1f}%\n'
        f'Сделок: {results["completed"]} | Win: {results["win_rate"]:.0f}% | DD: {results["max_dd"]:.1f}%\n'
        f'По сигналу: {results["signal_exits"]} | По стопу: {results["stop_exits"]} | '
        f'Ср.срок: {results["avg_bars"]:.0f}д | Ср.доход: {results["avg_return"]:.1f}%'
    )
    ax2.text(0.02, 0.98, text, transform=ax2.transAxes, fontsize=9,
            verticalalignment='top', fontfamily='monospace',
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
    
    plt.tight_layout()
    plt.savefig(f'hmm_{ticker}_strategy.png', dpi=150, bbox_inches='tight')
    plt.show()
    logger.info(f'График сохранён: hmm_{ticker}_strategy.png')


if __name__ == '__main__':
    loader = OsEngineLoader()
    
    ticker = 'Аэрофлот'
    logger.info(f'Загрузка: {ticker}')
    df = loader.load(ticker)
    daily = loader.to_daily(df)
    logger.info(f'Загружено: {len(daily)} дней')
    
    X, y, close, high, low, dates = prepare_features(daily)
    logger.info(f'После очистки: {len(X)} дней, {dates[0]} — {dates[-1]}')
    
    # Train/test
    split = int(len(X) * 0.7)
    X_train, X_test = X[:split], X[split:]
    close_train, close_test = close[:split], close[split:]
    high_train, high_test = high[:split], high[split:]
    low_train, low_test = low[:split], low[split:]
    dates_test = dates[split:]
    
    logger.info(f'Train: {len(X_train)}д | Test: {len(X_test)}д')
    
    # HMM
    model = train_hmm(X_train)
    states_train = model.predict(X_train)
    states_test = model.predict(X_test)
    
    # Находим UP-режим на train
    regime_returns = {}
    for s in range(model.n_components):
        mask = states_train == s
        if mask.sum() > 3:
            regime_returns[s] = float(np.mean(np.diff(close_train[mask]) / close_train[mask][:-1]))
    
    up_state = max(regime_returns, key=regime_returns.get)
    logger.info(f'UP-режим на train: State {up_state} (avg={regime_returns[up_state]:.4%})')
    for s, r in sorted(regime_returns.items(), key=lambda x: x[1], reverse=True):
        logger.info(f'  State {s}: avg_return={r:.4%}')
    
    # Бэктест на test с ATR-стопом
    results = backtest_with_atr_stop(
        model, X_test, close_test, high_test, low_test,
        up_state=up_state, atr_mult=2.0, breakeven_pct=3.0
    )
    
    logger.info(f'\n{"="*50}')
    logger.info(f'РЕЗУЛЬТАТЫ НА ТЕСТЕ')
    logger.info(f'{"="*50}')
    logger.info(f'Доходность: {results["total_return"]:.1f}%')
    logger.info(f'B&H:        {results["bh_return"]:.1f}%')
    logger.info(f'Дельта:     {results["delta"]:.1f}%')
    logger.info(f'Сделок:     {results["completed"]}')
    logger.info(f'Win rate:   {results["win_rate"]:.0f}%')
    logger.info(f'Max DD:     {results["max_dd"]:.1f}%')
    logger.info(f'По сигналу: {results["signal_exits"]}')
    logger.info(f'По стопу:   {results["stop_exits"]}')
    logger.info(f'Ср.срок:    {results["avg_bars"]:.0f}д')
    logger.info(f'Ср.доход:   {results["avg_return"]:.1f}%')
    
    # График
    results['states'] = states_test
    results['dates'] = dates_test
    plot_results(results, ticker, dates_test)
