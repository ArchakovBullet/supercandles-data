#!/usr/bin/env python3
"""Проверка сигналов парной торговли и уведомление в VK."""
import sys
import json
from pathlib import Path
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

# Добавляем пути
sys.path.insert(0, '/root/finlab')
sys.path.insert(0, '/root/finlab/FinLabPy')

import pandas as pd
import numpy as np
import vk_api

# ========== КОНФИГ ==========
TOKEN = "vk1.a.SlI9YR5W8dTnTYhVLlhNxXEmgDo6rImtWM1jEIpsZKb9KR8EB_x325YDm_Piu1QZffsffqKethgXWlBH3G0e_6h9DUmZEVzbCmXajTm3jW33hE1F49dUOVtjHGRLYN_5pYOnLN0ZiFpdu_DVVqPHLfShNWDBN1prFS7Yf1ec-PE75C_hhs5Mo7SANbnE_uWzA3dGP3_l3So8HfcUVW3f8A"
ADMIN_ID = 497763452

CANDLES_DIR = Path('/root/finlab/data/candles')
CONFIG_FILE = Path('/root/finlab/FinLabPy/My_Indicators/pairs_config.json')
STATE_FILE = Path('/root/finlab/logs/pair_signals_state.json')

# Порог для сигнала (Z-score)
SIGNAL_THRESHOLD = 2.0

# Таймфрейм для сигналов (M10 — самый быстрый)
TIMEFRAME = 'M10'


def load_config():
    """Загрузить конфигурацию пар."""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {'pairs': {}}


def load_state():
    """Загрузить предыдущее состояние сигналов."""
    if STATE_FILE.exists():
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {}


def save_state(state):
    """Сохранить текущее состояние сигналов."""
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2, default=str)


def calculate_zscore(df_a, df_b, window=20):
    """Рассчитать текущий Z-score для пары."""
    from My_Indicators.pairs_trading import calculate_spread, calculate_zscore
    
    # Выравнивание по датам
    if 'begin' in df_a.columns:
        df_a['date'] = pd.to_datetime(df_a['begin'])
    if 'begin' in df_b.columns:
        df_b['date'] = pd.to_datetime(df_b['begin'])
    
    merged = pd.merge(
        df_a[['date', 'close']].rename(columns={'close': 'price_a'}),
        df_b[['date', 'close']].rename(columns={'close': 'price_b'}),
        on='date', how='inner'
    ).dropna()
    
    if len(merged) < window + 1:
        return None
    
    # Спред
    spread, beta = calculate_spread(merged['price_a'], merged['price_b'], log_spread=True)
    
    # Z-score
    zscore = calculate_zscore(spread, window)
    
    return {
        'current_zscore': round(zscore.iloc[-1], 2),
        'current_spread': round(spread.iloc[-1], 4),
        'zscore_series': zscore,
        'spread_series': spread,
        'merged': merged
    }


def check_signals():
    """Проверить сигналы для активных пар."""
    config = load_config()
    state = load_state()
    
    signals = []
    
    # Получаем активные пары (ADF < 0.05)
    active_pairs = []
    for pair_name, pair_data in config.get('pairs', {}).items():
        if pair_name.endswith(f'_{TIMEFRAME}'):
            adf_pvalue = pair_data.get('adf', {}).get('p_value', 1.0)
            if adf_pvalue < 0.05:
                active_pairs.append(pair_name)
    
    print(f"Активные пары ({TIMEFRAME}): {len(active_pairs)}")
    
    for pair_name in active_pairs:
        # Извлекаем тикеры
        base_pair = pair_name.replace(f'_{TIMEFRAME}', '')
        if '-' in base_pair:
            ticker_a, ticker_b = base_pair.split('-')
        else:
            continue
        
        file_a = CANDLES_DIR / f"{ticker_a}_{TIMEFRAME}.parquet"
        file_b = CANDLES_DIR / f"{ticker_b}_{TIMEFRAME}.parquet"
        
        if not file_a.exists() or not file_b.exists():
            continue
        
        try:
            df_a = pd.read_parquet(file_a)
            df_b = pd.read_parquet(file_b)
            
            # Получаем оптимизированные параметры
            pair_data = config['pairs'][pair_name]
            window = pair_data.get('best_params', {}).get('window', 20)
            entry_z = pair_data.get('best_params', {}).get('entry_z', 2.0)
            
            result = calculate_zscore(df_a, df_b, window=window)
            
            if result:
                current_z = result['current_zscore']
                prev_state = state.get(pair_name, {}).get('zscore', 0)
                
                # Проверяем пересечение порога
                if abs(current_z) >= entry_z and abs(prev_state) < entry_z:
                    # Новый сигнал!
                    direction = "🔴 ШОРТ" if current_z > 0 else "🟢 ЛОНГ"
                    signals.append({
                        'pair': base_pair,
                        'zscore': current_z,
                        'direction': direction,
                        'time': datetime.now().strftime('%H:%M:%S')
                    })
                
                # Обновляем состояние
                state[pair_name] = {
                    'zscore': current_z,
                    'last_checked': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
        
        except Exception as e:
            print(f"❌ {pair_name}: {e}")
    
    save_state(state)
    return signals


def send_vk_message(vk, peer_id, message):
    """Отправить сообщение в VK."""
    try:
        vk.messages.send(
            peer_id=peer_id,
            message=message,
            random_id=int(datetime.now().timestamp() * 1000)
        )
        return True
    except Exception as e:
        print(f"❌ Ошибка отправки VK: {e}")
        return False


def main():
    """Основная функция."""
    print("=" * 60)
    print("ПРОВЕРКА СИГНАЛОВ ПАРНОЙ ТОРГОВЛИ")
    print(f"Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # Инициализация VK
    vk_session = vk_api.VkApi(token=TOKEN)
    vk = vk_session.get_api()
    
    # Проверить сигналы
    signals = check_signals()
    
    if signals:
        message_lines = ["🎯 Сигналы парной торговли:", ""]
        for s in signals:
            message_lines.append(f"{s['direction']} {s['pair']}: Z={s['zscore']} ({s['time']})")
        
        message = "\n".join(message_lines)
        print("\n" + message)
        
        if send_vk_message(vk, ADMIN_ID, message):
            print("\n✅ VK-уведомление отправлено")
        else:
            print("\n❌ Ошибка отправки VK")
    else:
        print("\n✅ Нет новых сигналов")
    
    print("\n✅ Проверка завершена")


if __name__ == '__main__':
    main()
