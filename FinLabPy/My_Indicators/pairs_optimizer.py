"""
Оптимизация параметров парной торговли с walk-forward подходом.
Включает ADF-тест, коинтеграцию, фильтр ADX.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
import json
import warnings
warnings.filterwarnings('ignore')

# Для ADF-теста и коинтеграции
from statsmodels.tsa.stattools import adfuller, coint


def calculate_adx(df, period=14):
    """Расчёт ADX для фильтра тренда"""
    high = df['high']
    low = df['low']
    close = df['close']
    
    # True Range
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    
    # Направленное движение
    up_move = high - high.shift(1)
    down_move = low.shift(1) - low
    
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
    
    plus_di = 100 * pd.Series(plus_dm, index=df.index).rolling(period).sum() / atr
    minus_di = 100 * pd.Series(minus_dm, index=df.index).rolling(period).sum() / atr
    
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
    adx = dx.rolling(period).mean()
    
    return adx


def test_adf(spread):
    """ADF-тест на стационарность спреда"""
    try:
        result = adfuller(spread.dropna(), autolag='AIC')
        return {
            'adf_statistic': round(result[0], 4),
            'p_value': round(result[1], 4),
            'critical_values': {k: round(v, 4) for k, v in result[4].items()},
            'is_stationary': result[1] < 0.05
        }
    except Exception as e:
        return {
            'adf_statistic': None,
            'p_value': None,
            'critical_values': None,
            'is_stationary': False
        }


def test_cointegration(price_a, price_b):
    """Тест коинтеграции Энгла-Грейнджера"""
    try:
        # Логарифмируем
        log_a = np.log(price_a)
        log_b = np.log(price_b)
        
        # Тест коинтеграции
        coint_t, p_value, _ = coint(log_a, log_b)
        
        return {
            'coint_statistic': round(coint_t, 4),
            'p_value': round(p_value, 4),
            'is_cointegrated': p_value < 0.05
        }
    except Exception as e:
        return {
            'coint_statistic': None,
            'p_value': None,
            'is_cointegrated': False
        }


def calculate_pnl_metrics(trades):
    """Расчёт метрик PnL для оптимизации"""
    if not trades:
        return {
            'total_pnl': 0,
            'win_rate': 0,
            'sharpe': 0,
            'max_drawdown': 0,
            'num_trades': 0
        }
    
    pnl_values = [t.get('pnl', 0) for t in trades if 'pnl' in t]
    
    if not pnl_values:
        return {
            'total_pnl': 0,
            'win_rate': 0,
            'sharpe': 0,
            'max_drawdown': 0,
            'num_trades': 0
        }
    
    pnl_series = pd.Series(pnl_values)
    win_rate = (pnl_series > 0).sum() / len(pnl_series)
    total_pnl = pnl_series.sum()
    
    # Sharpe ratio (считаем на сериях PnL)
    if len(pnl_series) > 1:
        sharpe = pnl_series.mean() / pnl_series.std() if pnl_series.std() > 0 else 0
    else:
        sharpe = 0
    
    # Максимальная просадка
    cumsum = pnl_series.cumsum()
    max_drawdown = (cumsum - cumsum.cummax()).min()
    
    return {
        'total_pnl': round(total_pnl, 4),
        'win_rate': round(win_rate, 3),
        'sharpe': round(sharpe, 3),
        'max_drawdown': round(max_drawdown, 4),
        'num_trades': len(trades)
    }


def backtest_pair(merged, window=20, entry_z=2.0, exit_z=0.5, use_filter=False, adx_threshold=25):
    """Бэктест парной торговли с заданными параметрами.
    Принимает merged DataFrame с колонками: begin, price_a, price_b"""
    
    if len(merged) < window + 1:
        return None
    
    # Логарифмический спред
    log_a = np.log(merged['price_a'])
    log_b = np.log(merged['price_b'])
    spread = log_a - log_b
    
    # Z-score
    spread_mean = spread.rolling(window).mean()
    spread_std = spread.rolling(window).std()
    zscore = (spread - spread_mean) / spread_std
    
    # Генерация сделок
    position = 0  # 0=нет, 1=лонг спреда, -1=шорт спреда
    trades = []
    
    for i in range(window, len(merged)):
        if pd.isna(zscore.iloc[i]):
            continue
        
        z = zscore.iloc[i]
        
        if position == 0:
            if z < -entry_z:
                position = 1
                trades.append({
                    'entry_date': str(merged['begin'].iloc[i]),
                    'entry_z': round(z, 2),
                    'direction': 'LONG_SPREAD',
                    'entry_price_a': merged['price_a'].iloc[i],
                    'entry_price_b': merged['price_b'].iloc[i]
                })
            elif z > entry_z:
                position = -1
                trades.append({
                    'entry_date': str(merged['begin'].iloc[i]),
                    'entry_z': round(z, 2),
                    'direction': 'SHORT_SPREAD',
                    'entry_price_a': merged['price_a'].iloc[i],
                    'entry_price_b': merged['price_b'].iloc[i]
                })
        elif position == 1 and z > -exit_z:
            trades[-1]['exit_date'] = str(merged['begin'].iloc[i])
            trades[-1]['exit_z'] = round(z, 2)
            trades[-1]['exit_price_a'] = merged['price_a'].iloc[i]
            trades[-1]['exit_price_b'] = merged['price_b'].iloc[i]
            # PnL для лонг спреда: покупаем A, продаём B
            trades[-1]['pnl'] = (merged['price_a'].iloc[i] / trades[-1]['entry_price_a'] - 
                                 merged['price_b'].iloc[i] / trades[-1]['entry_price_b'])
            position = 0
        elif position == -1 and z < exit_z:
            trades[-1]['exit_date'] = str(merged['begin'].iloc[i])
            trades[-1]['exit_z'] = round(z, 2)
            trades[-1]['exit_price_a'] = merged['price_a'].iloc[i]
            trades[-1]['exit_price_b'] = merged['price_b'].iloc[i]
            # PnL для шорт спреда: продаём A, покупаем B
            trades[-1]['pnl'] = -(merged['price_a'].iloc[i] / trades[-1]['entry_price_a'] - 
                                  merged['price_b'].iloc[i] / trades[-1]['entry_price_b'])
            position = 0
    
    # Закрыть открытую позицию
    if position != 0 and trades:
        trades[-1]['exit_date'] = str(merged['begin'].iloc[-1])
        trades[-1]['exit_z'] = round(zscore.iloc[-1], 2)
        trades[-1]['exit_price_a'] = merged['price_a'].iloc[-1]
        trades[-1]['exit_price_b'] = merged['price_b'].iloc[-1]
        if position == 1:
            trades[-1]['pnl'] = (merged['price_a'].iloc[-1] / trades[-1]['entry_price_a'] - 
                                 merged['price_b'].iloc[-1] / trades[-1]['entry_price_b'])
        else:
            trades[-1]['pnl'] = -(merged['price_a'].iloc[-1] / trades[-1]['entry_price_a'] - 
                                  merged['price_b'].iloc[-1] / trades[-1]['entry_price_b'])
    
    return trades


def optimize_pair(df_a, df_b, pair_name=""):
    """Оптимизация параметров пары с walk-forward подходом"""
    # Выравнивание по датам
    merged = pd.merge(
        df_a[['begin', 'close']].rename(columns={'close': 'price_a'}),
        df_b[['begin', 'close']].rename(columns={'close': 'price_b'}),
        on='begin', how='inner'
    ).dropna()
    
    if len(merged) < 100:
        return None
    
    # Разделение на train/test (walk-forward)
    train_size = int(len(merged) * 0.7)
    train_data = merged.iloc[:train_size]
    test_data = merged.iloc[train_size:]
    
    # Параметры для перебора
    windows = [10, 15, 20, 25, 30, 40, 50, 60]
    entry_z_scores = [1.5, 2.0, 2.5, 3.0]
    exit_z_scores = [0.0, 0.5, 1.0]
    
    best_params = None
    best_score = -np.inf
    
    # Grid search на train
    for window in windows:
        for entry_z in entry_z_scores:
            for exit_z in exit_z_scores:
                trades = backtest_pair(
                    train_data, window=window, 
                    entry_z=entry_z, exit_z=exit_z, 
                    use_filter=False
                )
                if trades:
                    metrics = calculate_pnl_metrics(trades)
                    # Критерий: Sharpe ratio
                    score = metrics['sharpe']
                    if score > best_score:
                        best_score = score
                        best_params = {
                            'window': window,
                            'entry_z': entry_z,
                            'exit_z': exit_z
                        }
    
    if not best_params:
        best_params = {'window': 20, 'entry_z': 2.0, 'exit_z': 0.5}
    
    # Тест на out-of-sample
    test_trades = backtest_pair(
        test_data, 
        window=best_params['window'],
        entry_z=best_params['entry_z'],
        exit_z=best_params['exit_z'],
        use_filter=False
    )
    
    test_metrics = calculate_pnl_metrics(test_trades) if test_trades else {}
    
    # Если сделок меньше 5, считаем оптимизацию неудачной
    if test_metrics.get('num_trades', 0) < 5:
        # Пробуем другие параметры или возвращаем None
        best_params = None
        best_score = -np.inf
        # Расширенный перебор с меньшим порогом входа
        for window in [20, 25, 30, 40]:
            for entry_z in [1.5, 2.0]:
                for exit_z in [0.0, 0.5]:
                    trades = backtest_pair(
                        train_data, window=window,
                        entry_z=entry_z, exit_z=exit_z,
                        use_filter=False
                    )
                    if trades:
                        metrics = calculate_pnl_metrics(trades)
                        if metrics['num_trades'] >= 5:
                            score = metrics['sharpe']
                            if score > best_score:
                                best_score = score
                                best_params = {
                                    'window': window,
                                    'entry_z': entry_z,
                                    'exit_z': exit_z
                                }
        
        if best_params:
            test_trades = backtest_pair(
                test_data,
                window=best_params['window'],
                entry_z=best_params['entry_z'],
                exit_z=best_params['exit_z'],
                use_filter=False
            )
            test_metrics = calculate_pnl_metrics(test_trades) if test_trades else {}
    
    # ADF-тест на последних 252 днях (1 год)
    spread = np.log(merged['price_a']) - np.log(merged['price_b'])
    # Используем последние 252 дня или весь период, если данных меньше
    adf_window = min(252, len(spread))
    spread_adf = spread.iloc[-adf_window:]
    adf_result = test_adf(spread_adf)
    
    # Коинтеграция
    coint_result = test_cointegration(merged['price_a'], merged['price_b'])
    
    return {
        'pair_name': pair_name,
        'best_params': best_params if best_params else {'window': 20, 'entry_z': 2.0, 'exit_z': 0.5},
        'train_score': round(best_score, 3),
        'test_metrics': test_metrics,
        'adf': adf_result,
        'cointegration': coint_result,
        'total_rows': len(merged),
        'last_optimized': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }


def save_pair_config(config, file_path=None):
    """Сохранить конфигурацию пары в JSON"""
    if file_path is None:
        file_path = Path("/root/finlab/FinLabPy/My_Indicators/pairs_config.json")
    
    # Загрузить существующий конфиг, если есть
    if file_path.exists():
        with open(file_path, 'r') as f:
            all_configs = json.load(f)
    else:
        all_configs = {'pairs': {}}
    
    # Обновить конфиг пары
    pair_name = config.get('pair_name', '')
    if pair_name:
        all_configs['pairs'][pair_name] = config
        all_configs['last_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # Сохранить
    with open(file_path, 'w') as f:
        json.dump(all_configs, f, indent=2, default=str)
    
    return file_path


if __name__ == '__main__':
    print("Модуль оптимизации парной торговли")
    print("Использование: from My_Indicators.pairs_optimizer import optimize_pair, save_pair_config")
