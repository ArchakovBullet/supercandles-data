"""
HMM + SuperTrend стратегия для Аэрофлота.
Вход только когда: HMM UP-режим И SuperTrend направление UP.
ATR-стоп + трейлинг-безубыток.

Использование:
    python FinLabPy/Strategies/hmm_aeroflot_v2.py
"""
import os
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent if '__file__' in dir() else Path('.').absolute()
sys.path.insert(0, str(project_root))

import numpy as np
import polars as pl
import matplotlib.pyplot as plt
from hmmlearn import hmm as hmmlearn_hmm
import talib

from FinLabPy.DataCollectors.osengine_loader import OsEngineLoader
from FinLabPy.My_Indicators.technical_features import add_technical_features
from FinLabPy.Utils import setup_logger

logger = setup_logger('hmm_aeroflot_v2')


def compute_super_trend(high, low, close, period=10, multiplier=3.0):
    """SuperTrend: линия + направление (+1 UP, -1 DOWN)."""
    atr = talib.ATR(high, low, close, timeperiod=period)
    hl_avg = (high + low) / 2
    upper = hl_avg + multiplier * atr
    lower = hl_avg - multiplier * atr
    
    n = len(close)
    st_line = np.zeros(n)
    st_dir = np.zeros(n)
    
    for i in range(1, n):
        upper[i] = upper[i] if upper[i] < upper[i-1] or close[i-1] > upper[i-1] else upper[i-1]
        lower[i] = lower[i] if lower[i] > lower[i-1] or close[i-1] < lower[i-1] else lower[i-1]
        
        if close[i] > upper[i-1]:
            st_dir[i] = 1
            st_line[i] = lower[i]
        elif close[i] < lower[i-1]:
            st_dir[i] = -1
            st_line[i] = upper[i]
        else:
            st_dir[i] = st_dir[i-1]
            st_line[i] = lower[i] if st_dir[i] == 1 else upper[i]
    
    return st_line, st_dir


def prepare_features_v2(df: pl.DataFrame) -> tuple:
    """
    Расширенные признаки: 9 базовых + SuperTrend направление + ADX тренд + RSI зоны.
    Всего 12 признаков.
    """
    df = add_technical_features(df)
    
    close = df['close'].to_numpy().astype(np.float64)
    high = df['high'].to_numpy().astype(np.float64)
    low = df['low'].to_numpy().astype(np.float64)
    volume = df['volume'].to_numpy().astype(np.float64)
    dates = df['date'].to_list()
    
    # SuperTrend
    st_line, st_dir = compute_super_trend(high, low, close, period=10, multiplier=3.0)
    
    # ADX тренд
    adx = talib.ADX(high, low, close, timeperiod=14)
    adx_trend = (adx > 25).astype(float)  # 1 = тренд, 0 = флэт
    
    # RSI зоны
    rsi = talib.RSI(close, timeperiod=14)
    rsi_overbought = (rsi > 70).astype(float)
    rsi_oversold = (rsi < 30).astype(float)
    
    # Базовые признаки
    base_features = [
        'returns', 'volatility', 'volume_ratio', 'trend_strength',
        'price_vs_sma20', 'price_vs_sma50', 'rsi', 'macd_hist', 'bb_position'
    ]
    
    X_base = df.select(base_features).to_numpy().astype(np.float64)
    y = df['future_returns_1d'].to_numpy().astype(np.float64)
    
    # Объединяем
    X = np.column_stack([
        X_base,
        st_dir,           # Направление SuperTrend
        adx_trend,        # ADX > 25
        rsi_overbought,   # RSI > 70
    ])
    
    # Чистим
    mask = ~np.isnan(X).any(axis=1) & ~np.isinf(X).any(axis=1)
    mask &= ~np.isnan(y) & ~np.isinf(y)
    
    return (X[mask], y[mask], close[mask], high[mask], low[mask],
            [d for i, d in enumerate(dates) if mask[i]],
            st_line[mask], st_dir[mask], adx[mask])


def train_hmm(X, n_states=5):
    """Обучает HMM. 5 состояний для более тонкого разделения."""
    model = hmmlearn_hmm.GaussianHMM(
        n_components=n_states,
        covariance_type='full',
        n_iter=2000,
        random_state=42,
        tol=1e-6,
    )
    model.fit(X)
    return model


def backtest_combined(model, X, close, high, low, up_state, st_line, st_dir, adx,
                      atr_mult=2.0, breakeven_pct=3.0):
    """
    Комбинированная стратегия:
    - Вход: HMM == up_state И SuperTrend UP (st_dir == 1)
    - Выход: HMM != up_state ИЛИ SuperTrend DOWN (st_dir == -1)
    - Стоп: ATR-стоп + трейлинг-безубыток
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
    
    for i in range(1, n):
        equity[i] = equity[i-1]
        
        # В позиции — проверяем стоп
        if position == 1:
            current_ret = (close[i] - entry_price) / entry_price * 100
            
            # Трейлинг-безубыток
            if current_ret >= breakeven_pct:
                stop_level = max(stop_level, entry_price)
            
            # Стоп
            if low[i] <= stop_level:
                ret = (stop_level - entry_price) / entry_price
                equity[i] = equity[i-1] * (1 + ret)
                position = 0
                stop_exits += 1
                trades.append({
                    'type': 'STOP', 'bar': i, 'price': stop_level,
                    'return': ret, 'bars_held': i - entry_bar,
                })
                continue
        
        # Комбинированный сигнал входа
        hmm_up = (states[i] == up_state)
        st_up = (st_dir[i] == 1)
        buy_signal = hmm_up and st_up
        
        # Комбинированный сигнал выхода
        hmm_exit = (states[i] != up_state)
        st_exit = (st_dir[i] == -1)
        sell_signal = hmm_exit or st_exit
        
        if buy_signal and position == 0:
            position = 1
            entry_price = close[i]
            entry_bar = i
            stop_level = entry_price - atr_mult * atr[i]
            trades.append({'type': 'BUY', 'bar': i, 'price': close[i]})
        
        elif sell_signal and position == 1:
            ret = (close[i] - entry_price) / entry_price
            equity[i] = equity[i-1] * (1 + ret)
            position = 0
            signal_exits += 1
            trades.append({
                'type': 'SIGNAL', 'bar': i, 'price': close[i],
                'return': ret, 'bars_held': i - entry_bar,
            })
        
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
        'completed': len(completed),
        'win_rate': len(wins) / max(len(completed), 1) * 100,
        'max_dd': float(max_dd * 100),
        'signal_exits': signal_exits,
        'stop_exits': stop_exits,
        'avg_bars': float(np.mean([t['bars_held'] for t in completed])) if completed else 0,
        'avg_return': float(np.mean([t['return'] for t in completed]) * 100) if completed else 0,
        'equity': equity,
        'states': states,
        'close': close,
        'high': high,
        'low': low,
        'st_line': st_line,
        'st_dir': st_dir,
        'adx': adx,
        'trades': trades,
    }


def plot_results(results, ticker, dates):
    """График с ценой, HMM-режимами, SuperTrend, точками входа/выхода."""
    states = results['states']
    close = results['close']
    equity = results['equity']
    st_line = results['st_line']
    st_dir = results['st_dir']
    trades = results['trades']
    
    n = len(close)
    x = np.arange(n)
    
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(18, 10), 
                                    gridspec_kw={'height_ratios': [3, 1]})
    
    # HMM режимы — цветной фон
    colors = ['#FFE0E0', '#E0FFE0', '#E0E0FF', '#FFFFE0', '#FFE0FF']
    unique_states = sorted(set(states))
    for state in unique_states:
        mask = states == state
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
        
        color = colors[state % len(colors)]
        for s, e in segments:
            if e > s:
                ax1.axvspan(s, e, alpha=0.15, color=color)
    
    # Цена
    ax1.plot(x, close, 'k-', linewidth=1, label=f'{ticker}', zorder=5)
    
    # SuperTrend
    ax1.plot(x, st_line, 'b--', linewidth=1, alpha=0.8, label='SuperTrend')
    
    # Входы/выходы
    buys = [t for t in trades if t['type'] == 'BUY']
    exits = [t for t in trades if t['type'] in ('SIGNAL', 'STOP', 'END')]
    
    if buys:
        ax1.scatter([t['bar'] for t in buys], [t['price'] for t in buys],
                   c='lime', marker='^', s=150, zorder=10, edgecolors='green', 
                   linewidth=2, label=f'BUY ({len(buys)})')
    
    sig_ex = [t for t in exits if t['type'] == 'SIGNAL']
    stp_ex = [t for t in exits if t['type'] == 'STOP']
    
    if sig_ex:
        ax1.scatter([t['bar'] for t in sig_ex], [t['price'] for t in sig_ex],
                   c='blue', marker='v', s=120, zorder=10, edgecolors='darkblue',
                   linewidth=1.5, label=f'EXIT сигнал ({len(sig_ex)})')
    if stp_ex:
        ax1.scatter([t['bar'] for t in stp_ex], [t['price'] for t in stp_ex],
                   c='red', marker='v', s=120, zorder=10, edgecolors='darkred',
                   linewidth=1.5, label=f'EXIT стоп ({len(stp_ex)})')
    
    ax1.set_title(f'HMM + SuperTrend: {ticker} | 5 режимов | ATR-стоп 2× | Безубыток 3%',
                  fontsize=13, fontweight='bold')
    ax1.set_ylabel('Цена (₽)')
    ax1.legend(loc='upper left', fontsize=9)
    ax1.grid(True, alpha=0.3)
    
    # Эквити
    ax2.plot(x, equity, 'g-', linewidth=1.5, label=f'HMM+ST: {results["total_return"]:.1f}%')
    bh = (close - close[0]) / close[0] + 1
    ax2.plot(x, bh, 'k--', linewidth=1, alpha=0.5, label=f'B&H: {results["bh_return"]:.1f}%')
    ax2.axhline(y=1.0, color='gray', linestyle=':', alpha=0.5)
    ax2.set_xlabel('Бары (дни)')
    ax2.set_ylabel('Капитал (×)')
    ax2.legend(loc='upper left', fontsize=9)
    ax2.grid(True, alpha=0.3)
    
    text = (
        f'Δ={results["delta"]:.1f}% | Сделок: {results["completed"]} | '
        f'Win: {results["win_rate"]:.0f}% | DD: {results["max_dd"]:.1f}%\n'
        f'По сигналу: {results["signal_exits"]} | По стопу: {results["stop_exits"]} | '
        f'Срок: {results["avg_bars"]:.0f}д | Доход/сделку: {results["avg_return"]:.1f}%'
    )
    ax2.text(0.02, 0.98, text, transform=ax2.transAxes, fontsize=10,
            verticalalignment='top', fontfamily='monospace',
            bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.9))
    
    plt.tight_layout()
    plt.savefig(f'hmm_v2_{ticker}.png', dpi=150, bbox_inches='tight')
    plt.show()
    logger.info(f'График: hmm_v2_{ticker}.png')


if __name__ == '__main__':
    loader = OsEngineLoader()
    ticker = 'Аэрофлот'
    
    logger.info(f'Загрузка: {ticker}')
    df = loader.load(ticker)
    daily = loader.to_daily(df)
    
    logger.info('Подготовка расширенных признаков...')
    X, y, close, high, low, dates, st_line, st_dir, adx = prepare_features_v2(daily)
    logger.info(f'После очистки: {len(X)} дней, {dates[0]} — {dates[-1]}, признаков: {X.shape[1]}')
    
    # Train/test 70/30
    split = int(len(X) * 0.7)
    X_tr, X_te = X[:split], X[split:]
    close_tr, close_te = close[:split], close[split:]
    high_tr, high_te = high[:split], high[split:]
    low_tr, low_te = low[:split], low[split:]
    st_line_te = st_line[split:]
    st_dir_te = st_dir[split:]
    adx_te = adx[split:]
    dates_te = dates[split:]
    
    logger.info(f'Train: {len(X_tr)}д | Test: {len(X_te)}д')
    
    # HMM 5 состояний
    model = train_hmm(X_tr, n_states=5)
    states_tr = model.predict(X_tr)
    
    # Ищем UP-режим на train
    regime_ret = {}
    for s in range(5):
        mask = states_tr == s
        if mask.sum() > 5:
            regime_ret[s] = float(np.mean(np.diff(close_tr[mask]) / (close_tr[mask][:-1] + 1e-10)))
    
    up_state = max(regime_ret, key=regime_ret.get)
    logger.info(f'Режимы на train (5 состояний):')
    for s, r in sorted(regime_ret.items(), key=lambda x: x[1], reverse=True):
        cnt = (states_tr == s).sum()
        logger.info(f'  State {s}: avg={r:.4%}, дней={cnt}')
    logger.info(f'UP-режим: State {up_state}')
    
    # Бэктест
    results = backtest_combined(
        model, X_te, close_te, high_te, low_te,
        up_state=up_state, st_line=st_line_te, st_dir=st_dir_te, adx=adx_te,
        atr_mult=2.0, breakeven_pct=3.0
    )
    
    logger.info(f'\n{"="*50}')
    logger.info(f'РЕЗУЛЬТАТЫ')
    logger.info(f'{"="*50}')
    logger.info(f'Доходность: {results["total_return"]:.1f}%')
    logger.info(f'B&H:        {results["bh_return"]:.1f}%')
    logger.info(f'Δ (дельта): {results["delta"]:.1f}%')
    logger.info(f'Сделок:     {results["completed"]}')
    logger.info(f'Win rate:   {results["win_rate"]:.0f}%')
    logger.info(f'Max DD:     {results["max_dd"]:.1f}%')
    logger.info(f'По сигналу: {results["signal_exits"]}')
    logger.info(f'По стопу:   {results["stop_exits"]}')
    logger.info(f'Ср.срок:    {results["avg_bars"]:.0f}д')
    logger.info(f'Ср.доход:   {results["avg_return"]:.1f}%')
    
    # График
    plot_results(results, ticker, dates_te)
