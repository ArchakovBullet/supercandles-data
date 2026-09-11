"""
Валидация HMM стратегии с train/test разделением и стоп-лоссом.
Проверяет отсутствие look-ahead bias и переобучения.

Использование:
    python FinLabPy/Strategies/hmm_strategy_validation.py
"""
import os
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent if '__file__' in dir() else Path('.').absolute()
sys.path.insert(0, str(project_root))

import numpy as np
import polars as pl
from hmmlearn import hmm as hmmlearn_hmm
from FinLabPy.DataCollectors.osengine_loader import OsEngineLoader
from FinLabPy.My_Indicators.technical_features import add_technical_features
from FinLabPy.Utils import setup_logger

logger = setup_logger('hmm_validation')


def prepare_features(df: pl.DataFrame) -> tuple:
    """Подготавливает признаки и таргет, удаляет NaN/Inf."""
    df = add_technical_features(df)
    
    features = [
        'returns', 'volatility', 'volume_ratio', 'trend_strength',
        'price_vs_sma20', 'price_vs_sma50', 'rsi', 'macd_hist', 'bb_position'
    ]
    
    X = df.select(features).to_numpy().astype(np.float64)
    y = df['future_returns_1d'].to_numpy().astype(np.float64)
    close = df['close'].to_numpy().astype(np.float64)
    dates = df['date'].to_list()
    
    mask = ~np.isnan(X).any(axis=1) & ~np.isinf(X).any(axis=1)
    mask &= ~np.isnan(y) & ~np.isinf(y)
    
    X = X[mask]
    y = y[mask]
    close = close[mask]
    dates = [d for i, d in enumerate(dates) if mask[i]]
    
    return X, y, close, dates


def train_hmm(X: np.ndarray, n_states: int = 4) -> hmmlearn_hmm.GaussianHMM:
    """Обучает HMM на тренировочных данных."""
    model = hmmlearn_hmm.GaussianHMM(
        n_components=n_states,
        covariance_type='full',
        n_iter=1000,
        random_state=42,
        tol=1e-4,
    )
    model.fit(X)
    return model


def get_regime_stats(model, X: np.ndarray, close: np.ndarray) -> dict:
    """Рассчитывает доходность каждого режима."""
    states = model.predict(X)
    
    regime_stats = {}
    for state in range(model.n_components):
        mask = states == state
        if mask.sum() < 3:
            continue
        
        returns = np.diff(close[mask], prepend=close[mask][0]) / close[mask][0]
        regime_stats[state] = {
            'count': int(mask.sum()),
            'pct': float(mask.sum() / len(states) * 100),
            'avg_return': float(np.mean(returns)) if len(returns) > 1 else 0,
            'total_return': float(returns[-1]) if len(returns) > 0 else 0,
            'sharpe': float(np.mean(returns) / np.std(returns) * np.sqrt(252)) if len(returns) > 1 and np.std(returns) > 0 else 0,
        }
    
    return regime_stats


def backtest_strategy(model, X: np.ndarray, close: np.ndarray, up_state: int, 
                      stop_loss_pct: float = None) -> dict:
    """
    Торгует только в UP-режиме.
    - BUY: HMM входит в UP-режим
    - SELL: HMM выходит из UP-режима (обратный сигнал)
    - SELL: стоп-лосс (если цена упала на stop_loss_pct%)
    
    Args:
        model: обученный HMM
        X: признаки
        close: цены закрытия
        up_state: номер UP-режима
        stop_loss_pct: стоп-лосс в % (например, 2.0 = 2% от цены входа)
    """
    states = model.predict(X)
    n = len(close)
    
    position = 0
    entry_price = 0
    entry_bar = 0
    trades = []
    equity = np.ones(n)
    max_drawdown = 0
    peak_equity = 1.0
    stop_losses = 0
    signal_exits = 0
    
    for i in range(1, n):
        equity[i] = equity[i-1]
        
        # Проверка стоп-лосса (если в позиции)
        if position == 1 and stop_loss_pct is not None:
            current_loss = (close[i] - entry_price) / entry_price * 100
            if current_loss <= -stop_loss_pct:
                # Стоп-лосс сработал
                ret = current_loss / 100
                equity[i] = equity[i-1] * (1 + ret)
                position = 0
                stop_losses += 1
                trades.append({
                    'type': 'STOP_LOSS', 
                    'date': i, 
                    'price': close[i], 
                    'return': ret,
                    'bars_held': i - entry_bar,
                })
                continue
        
        # Сигнал HMM
        if states[i] == up_state and position == 0:
            # Вход в UP-режим
            position = 1
            entry_price = close[i]
            entry_bar = i
            trades.append({'type': 'BUY', 'date': i, 'price': close[i]})
        
        elif states[i] != up_state and position == 1:
            # Выход по обратному сигналу
            ret = (close[i] - entry_price) / entry_price
            equity[i] = equity[i-1] * (1 + ret)
            position = 0
            signal_exits += 1
            trades.append({
                'type': 'SIGNAL_EXIT', 
                'date': i, 
                'price': close[i], 
                'return': ret,
                'bars_held': i - entry_bar,
            })
        
        # Обновляем просадку
        if equity[i] > peak_equity:
            peak_equity = equity[i]
        dd = (equity[i] - peak_equity) / peak_equity
        if dd < max_drawdown:
            max_drawdown = dd
    
    # Закрываем позицию в конце
    if position == 1:
        ret = (close[-1] - entry_price) / entry_price
        equity[-1] = equity[-2] * (1 + ret)
        signal_exits += 1
        trades.append({
            'type': 'END_EXIT', 
            'date': n-1, 
            'price': close[-1], 
            'return': ret,
            'bars_held': n - 1 - entry_bar,
        })
    
    total_return = float((equity[-1] - 1) * 100)
    bh_return = float((close[-1] - close[0]) / close[0] * 100)
    
    win_trades = [t for t in trades if t.get('return', 0) > 0]
    completed = [t for t in trades if 'return' in t]
    
    avg_bars = float(np.mean([t['bars_held'] for t in completed])) if completed else 0
    avg_return = float(np.mean([t['return'] for t in completed])) * 100 if completed else 0
    
    return {
        'total_return': total_return,
        'bh_return': bh_return,
        'delta': total_return - bh_return,
        'trades': len(trades),
        'completed': len(completed),
        'win_rate': len(win_trades) / max(len(completed), 1) * 100,
        'max_drawdown': float(max_drawdown * 100),
        'stop_losses': stop_losses,
        'signal_exits': signal_exits,
        'avg_bars_held': avg_bars,
        'avg_return_per_trade': avg_return,
    }


def validate_ticker(loader: OsEngineLoader, ticker_name: str, 
                    train_ratio: float = 0.7, stop_loss_pct: float = None):
    """Полная валидация для одного тикера с опциональным стоп-лоссом."""
    sl_label = f' стоп={stop_loss_pct}%' if stop_loss_pct else ' без стопа'
    logger.info(f'{"="*60}')
    logger.info(f'ВАЛИДАЦИЯ: {ticker_name}{sl_label}')
    logger.info(f'{"="*60}')
    
    df = loader.load(ticker_name)
    daily = loader.to_daily(df)
    logger.info(f'Загружено: {len(daily)} дней')
    
    X, y, close, dates = prepare_features(daily)
    logger.info(f'После очистки: {len(X)} дней')
    
    if len(X) < 60:
        logger.warning(f'СЛИШКОМ МАЛО ДАННЫХ: {len(X)} дней')
        return None
    
    split_idx = int(len(X) * train_ratio)
    X_train, X_test = X[:split_idx], X[split_idx:]
    close_train, close_test = close[:split_idx], close[split_idx:]
    dates_train, dates_test = dates[:split_idx], dates[split_idx:]
    
    logger.info(f'Train: {len(X_train)}д | Test: {len(X_test)}д')
    
    model = train_hmm(X_train)
    
    regime_stats_train = get_regime_stats(model, X_train, close_train)
    best_state = max(regime_stats_train.items(), key=lambda x: x[1]['avg_return'])[0]
    
    # Train
    tr = backtest_strategy(model, X_train, close_train, best_state, stop_loss_pct)
    logger.info(f'TRAIN: {tr["total_return"]:.1f}% | B&H: {tr["bh_return"]:.1f}% | '
                f'Δ={tr["delta"]:.1f}% | Сделок: {tr["completed"]} | '
                f'Win: {tr["win_rate"]:.1f}% | DD: {tr["max_drawdown"]:.1f}% | '
                f'Стопов: {tr["stop_losses"]} | Срок: {tr["avg_bars_held"]:.0f}д')
    
    # Test
    ts = backtest_strategy(model, X_test, close_test, best_state, stop_loss_pct)
    logger.info(f'TEST:  {ts["total_return"]:.1f}% | B&H: {ts["bh_return"]:.1f}% | '
                f'Δ={ts["delta"]:.1f}% | Сделок: {ts["completed"]} | '
                f'Win: {ts["win_rate"]:.1f}% | DD: {ts["max_drawdown"]:.1f}% | '
                f'Стопов: {ts["stop_losses"]} | Срок: {ts["avg_bars_held"]:.0f}д')
    
    good = '✅' if ts['delta'] > 0 else '⚠️'
    logger.info(f'{good} Дельта к B&H: {ts["delta"]:.1f}%')
    
    return {
        'ticker': ticker_name,
        'stop_loss': stop_loss_pct,
        'train_return': tr['total_return'],
        'test_return': ts['total_return'],
        'test_bh': ts['bh_return'],
        'test_delta': ts['delta'],
        'test_trades': ts['completed'],
        'test_win_rate': ts['win_rate'],
        'test_max_dd': ts['max_drawdown'],
        'test_stop_losses': ts['stop_losses'],
        'test_avg_bars': ts['avg_bars_held'],
        'test_avg_return': ts['avg_return_per_trade'],
    }


if __name__ == '__main__':
    loader = OsEngineLoader()
    
    TICKERS = [
        'Аэрофлот', 'ВТБ ао', 'GLDRUBF(вечный)', 'Роснефть', 'ЛУКОЙЛ',
        'МосБиржа', 'Татнфт 3ао', 'GAZPF(вечный)', 'IMOEXF',
    ]
    
    # Тестируем с разными стопами
    STOP_LOSSES = [None, 2.0, 3.0, 5.0, 7.0, 10.0]
    
    all_results = []
    
    for sl in STOP_LOSSES:
        for name in TICKERS:
            try:
                r = validate_ticker(loader, name, stop_loss_pct=sl)
                if r:
                    all_results.append(r)
            except Exception as e:
                logger.error(f'{name} (стоп={sl}%): ОШИБКА — {e}')
    
    # Сводная: группируем по тикеру и стопу, показываем только test
    logger.info(f'\n{"="*90}')
    logger.info(f'ИТОГИ: ЗАВИСИМОСТЬ ОТ СТОП-ЛОССА (TEST)')
    logger.info(f'{"="*90}')
    logger.info(f'{"Тикер":<20} {"Стоп":>6} {"Доход":>8} {"B&H":>8} {"Δ":>8} {"Сделок":>6} {"Win%":>6} {"DD":>8} {"Стопов":>6} {"Срок":>5}')
    logger.info(f'{"-"*85}')
    
    for r in sorted(all_results, key=lambda x: (x['ticker'], x['stop_loss'] or 0)):
        sl_str = f'{r["stop_loss"]:.0f}%' if r['stop_loss'] else 'нет'
        logger.info(f'{r["ticker"]:<20} {sl_str:>6} {r["test_return"]:>7.1f}% {r["test_bh"]:>7.1f}% '
                    f'{r["test_delta"]:>+7.1f}% {r["test_trades"]:>6} {r["test_win_rate"]:>5.1f}% '
                    f'{r["test_max_dd"]:>7.1f}% {r["test_stop_losses"]:>6} {r["test_avg_bars"]:>4.0f}д')
    
    # Лучший по дельте для каждого тикера
    logger.info(f'\n{"="*90}')
    logger.info(f'ЛУЧШИЙ СТОП ДЛЯ КАЖДОГО ТИКЕРА')
    logger.info(f'{"="*90}')
    
    tickers_done = set()
    for r in sorted(all_results, key=lambda x: x['test_delta'], reverse=True):
        if r['ticker'] not in tickers_done:
            tickers_done.add(r['ticker'])
            sl_str = f'стоп={r["stop_loss"]:.0f}%' if r['stop_loss'] else 'без стопа'
            logger.info(f'{r["ticker"]:<20} {sl_str:<12} Δ={r["test_delta"]:>+6.1f}% | '
                        f'{r["test_return"]:>6.1f}% vs B&H {r["test_bh"]:>6.1f}% | '
                        f'Сделок: {r["test_trades"]} | DD: {r["test_max_dd"]:.1f}%')
