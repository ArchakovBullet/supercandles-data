"""
Торговый робот парной торговли (бумажный режим)
===================================================
Работает в фоновом режиме, проверяет сигналы по парам,
открывает/закрывает позиции в SQLite, отправляет VK-уведомления.

Управление:
- Файл-команда: /root/finlab/robots/robot_command.txt
  Команды: START, STOP, PAUSE, RESUME
- Кнопки Старт/Стоп в дашборде записывают команды в этот файл
"""
import json
import sqlite3
import time
import os
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

# ========== КОНФИГ ==========
ROOT = Path('/root/finlab')
CONFIG_PATH = ROOT / 'FinLabPy' / 'My_Indicators' / 'pairs_config.json'
CANDLES_DIR = ROOT / 'data' / 'candles'
DB_PATH = ROOT / 'robots' / 'pairs_robot.db'
COMMAND_FILE = ROOT / 'robots' / 'robot_command.txt'
STATE_FILE = ROOT / 'robots' / 'robot_state.json'

# VK
VK_TOKEN = os.getenv('VK_TOKEN', '')
VK_GROUP_ID = os.getenv('VK_GROUP_ID', '497763452')

# Настройки робота
DEPOSIT = 100_000  # Виртуальный капитал
VOLUME_TYPE = 'contracts'  # contracts / contract_currency / deposit_percent
VOLUME = 1.0  # 1 контракт/акция
CHECK_INTERVALS = {'M10': 600, 'H1': 3600}  # секунд
ENTRY_Z_DEFAULT = 2.0
EXIT_Z_DEFAULT = 0.5

# ========== БАЗА ДАННЫХ ==========
def init_db():
    """Создать таблицы в SQLite"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Таблица позиций
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pair_name TEXT NOT NULL,
            base_pair TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            direction TEXT NOT NULL,  -- LONG_SPREAD / SHORT_SPREAD
            volume REAL NOT NULL,
            entry_z REAL NOT NULL,
            entry_time TEXT NOT NULL,
            entry_price_a REAL,
            entry_price_b REAL,
            status TEXT DEFAULT 'OPEN',  -- OPEN / CLOSED
            exit_time TEXT,
            exit_z REAL,
            exit_price_a REAL,
            exit_price_b REAL,
            pnl REAL DEFAULT 0
        )
    ''')
    
    # Таблица сделок (журнал)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pair_name TEXT NOT NULL,
            base_pair TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            action TEXT NOT NULL,  -- OPEN / CLOSE
            direction TEXT,
            volume REAL,
            zscore REAL,
            price_a REAL,
            price_b REAL,
            pnl REAL DEFAULT 0,
            time TEXT NOT NULL
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ БД инициализирована")

# ========== РАСЧЁТ СИГНАЛОВ ==========
def calculate_zscore(price_a, price_b, window=20):
    """Рассчитать Z-score спреда"""
    try:
        if len(price_a) < window or len(price_b) < window:
            return None
        
        # Логарифмический спред
        import numpy as np
        log_a = np.log(price_a)
        log_b = np.log(price_b)
        spread = log_a - log_b
        
        # Z-score
        mean = spread.rolling(window=window).mean()
        std = spread.rolling(window=window).std()
        zscore = (spread - mean) / std
        
        return {
            'current_zscore': zscore.iloc[-1],
            'spread': spread.iloc[-1],
            'mean': mean.iloc[-1],
            'std': std.iloc[-1]
        }
    except Exception as e:
        print(f"❌ Z-score error: {e}")
        return None

# ========== VK-УВЕДОМЛЕНИЯ ==========
def send_vk_message(message):
    """Отправить сообщение в VK"""
    if not VK_TOKEN:
        print("❌ VK_TOKEN не настроен")
        return False
    
    url = 'https://api.vk.com/method/messages.send'
    params = {
        'access_token': VK_TOKEN,
        'peer_id': VK_GROUP_ID,
        'message': message,
        'random_id': 0,
        'v': '5.131'
    }
    r = requests.post(url, params=params, timeout=10)
    return r.status_code == 200

# ========== ЖУРНАЛ СДЕЛОК ==========
def log_trade(pair_name, base_pair, tf, action, direction, volume, zscore, price_a, price_b, pnl=0):
    """Записать сделку в SQLite"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO trades (pair_name, base_pair, timeframe, action, direction, volume, zscore, price_a, price_b, pnl, time)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (pair_name, base_pair, tf, action, direction, volume, zscore, price_a, price_b, pnl, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()
    conn.close()

# ========== ПОЗИЦИИ ==========
def get_open_positions():
    """Получить открытые позиции из БД"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM positions WHERE status = "OPEN"')
    positions = cursor.fetchall()
    conn.close()
    return positions

def open_position(pair_name, base_pair, tf, direction, volume, zscore, price_a, price_b):
    """Открыть позицию"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO positions (pair_name, base_pair, timeframe, direction, volume, entry_z, entry_time, entry_price_a, entry_price_b)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (pair_name, base_pair, tf, direction, volume, zscore, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), price_a, price_b))
    conn.commit()
    conn.close()
    
    # Журнал
    log_trade(pair_name, base_pair, tf, 'OPEN', direction, volume, zscore, price_a, price_b)
    
    # VK
    emoji = '🔴' if direction == 'SHORT_SPREAD' else '🟢'
    action = 'ШОРТ' if direction == 'SHORT_SPREAD' else 'ЛОНГ'
    message = f"🤖 РОБОТ: {emoji} {action} {base_pair}_{tf}: Z={zscore:.2f}"
    send_vk_message(message)
    print(f"✅ Открыта позиция: {message}")

def close_position(position_id, pair_name, base_pair, tf, zscore, price_a, price_b):
    """Закрыть позицию"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Получаем параметры позиции
    cursor.execute('SELECT direction, volume, entry_z, entry_price_a, entry_price_b FROM positions WHERE id = ?', (position_id,))
    pos = cursor.fetchone()
    if not pos:
        conn.close()
        return
    
    direction, volume, entry_z, entry_price_a, entry_price_b = pos
    
    # Рассчитываем PnL (бумажный)
    if direction == 'LONG_SPREAD':
        pnl = (price_a - entry_price_a) + (entry_price_b - price_b)
    else:
        pnl = (entry_price_a - price_a) + (price_b - entry_price_b)
    
    # Обновляем позицию
    cursor.execute('''
        UPDATE positions SET status = "CLOSED", exit_time = ?, exit_z = ?, exit_price_a = ?, exit_price_b = ?, pnl = ?
        WHERE id = ?
    ''', (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), zscore, price_a, price_b, pnl, position_id))
    conn.commit()
    conn.close()
    
    # Журнал
    log_trade(pair_name, base_pair, tf, 'CLOSE', direction, volume, zscore, price_a, price_b, pnl)
    
    # VK
    emoji = '🟢' if pnl > 0 else '🔴'
    message = f"🤖 РОБОТ: ЗАКРЫТИЕ {base_pair}_{tf}: PnL={pnl:+.4f} {emoji}"
    send_vk_message(message)
    print(f"✅ Закрыта позиция: {message}")

# ========== ПРОВЕРКА КОМАНД ==========
def process_command():
    """Проверить команду из файла"""
    if COMMAND_FILE.exists():
        cmd = COMMAND_FILE.read_text().strip().upper()
        if cmd:
            COMMAND_FILE.write_text('')
            return cmd
    return None

# ========== ОСНОВНОЙ ЦИКЛ ==========
def main():
    print("=" * 60)
    print(f"🤖 РОБОТ ПАРНОЙ ТОРГОВЛИ | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    print(f"Депозит: {DEPOSIT} ₽")
    print(f"Объём: {VOLUME} {VOLUME_TYPE}")
    print(f"Проверка: M10 — каждые {CHECK_INTERVALS['M10']//60} мин, H1 — каждые {CHECK_INTERVALS['H1']//3600} ч")
    print("=" * 60)
    
    # Инициализация БД
    init_db()
    
    # Загружаем конфиг пар
    with open(CONFIG_PATH, 'r') as f:
        pairs_config = json.load(f)
    
    running = True
    last_check = {'M10': 0, 'H1': 0}
    
    while running:
        try:
            # Проверяем команды
            cmd = process_command()
            if cmd == 'STOP':
                print("🛑 Команда STOP: закрываем все позиции")
                for pos in get_open_positions():
                    close_position(pos[0], pos[1], pos[2], pos[3], 0, 0, 0)
                running = False
                break
            elif cmd == 'PAUSE':
                print("⏸️ Команда PAUSE: робот приостановлен")
                running = False
                break
            
            current_time = time.time()
            
            # Проверяем сигналы по ТФ
            for tf, interval in CHECK_INTERVALS.items():
                if current_time - last_check[tf] >= interval:
                    check_signals_by_tf(pairs_config, tf)
                    last_check[tf] = current_time
            
            time.sleep(1)
        
        except KeyboardInterrupt:
            print("🛑 Остановлено пользователем")
            break
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            time.sleep(5)
    
    print("✅ Робот остановлен")

def check_signals_by_tf(pairs_config, tf):
    """Проверить сигналы по парам на конкретном ТФ"""
    print(f"\n📊 Проверка сигналов {tf}...")
    
    for pair_name, pair_data in pairs_config.get('pairs', {}).items():
        if not pair_name.endswith(f'_{tf}'):
            continue
        
        base_pair = pair_name.replace(f'_{tf}', '')
        if '-' not in base_pair:
            continue
        
        ticker_a, ticker_b = base_pair.split('-')
        file_a = CANDLES_DIR / f'{ticker_a}_{tf}.parquet'
        file_b = CANDLES_DIR / f'{ticker_b}_{tf}.parquet'
        
        if not file_a.exists() or not file_b.exists():
            continue
        
        try:
            df_a = pd.read_parquet(file_a)
            df_b = pd.read_parquet(file_b)
            
            # Параметры
            window = pair_data.get('best_params', {}).get('window', 20)
            entry_z = pair_data.get('best_params', {}).get('entry_z', ENTRY_Z_DEFAULT)
            exit_z = pair_data.get('best_params', {}).get('exit_z', EXIT_Z_DEFAULT)
            
            # Z-score
            result = calculate_zscore(df_a['close'], df_b['close'], window=window)
            if not result:
                continue
            
            current_z = result['current_zscore']
            price_a = df_a['close'].iloc[-1]
            price_b = df_b['close'].iloc[-1]
            
            # Проверяем открытые позиции
            open_positions = get_open_positions()
            has_position = any(p[1] == pair_name and p[3] == tf for p in open_positions)
            
            if not has_position:
                # Проверяем вход
                if current_z >= entry_z:
                    open_position(pair_name, base_pair, tf, 'SHORT_SPREAD', VOLUME, current_z, price_a, price_b)
                elif current_z <= -entry_z:
                    open_position(pair_name, base_pair, tf, 'LONG_SPREAD', VOLUME, current_z, price_a, price_b)
            else:
                # Проверяем выход
                if abs(current_z) <= exit_z:
                    for pos in open_positions:
                        if pos[1] == pair_name and pos[3] == tf:
                            close_position(pos[0], pair_name, base_pair, tf, current_z, price_a, price_b)
        
        except Exception as e:
            print(f"  ❌ {pair_name}: {e}")

if __name__ == '__main__':
    main()
