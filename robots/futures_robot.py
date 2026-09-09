"""
Торговый робот фьючерсов (бумажный режим)
===================================================
Использует логику из Сканера фьючерсов:
- 1D (стратегия) + 4H (тактика) + 1H (точка входа)
- Вход: скор >= 60 (или 80 в кризис)
- Выход: обратный сигнал или скор < 40
- Стоп: 1×ATR (2×ATR в кризис)
- Позиция: 1 контракт
"""
import json
import sqlite3
import time
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import numpy as np

# Добавляем FinLabPy в путь
sys.path.insert(0, '/root/finlab/FinLabPy')

from My_Indicators.unified_scanner import get_unified_scanner_verdict
from My_Indicators.volume_analyzer import VolumeAnomalyDetector
from My_Indicators.herrick_payoff_index import calculate_hpi

# ========== КОНФИГ ==========
ROOT = Path('/root/finlab')
DATA_ROOT = ROOT / 'data'
DB_PATH = ROOT / 'robots' / 'futures_robot.db'
STATE_FILE = ROOT / 'robots' / 'futures_robot_state.json'
COMMAND_FILE = ROOT / 'robots' / 'futures_robot_command.txt'

# Пороги
ENTRY_SCORE = 60
EXIT_SCORE = 40
CRISIS_ENTRY_SCORE = 80
CRISIS_EXIT_SCORE = 40

# VK
from dotenv import load_dotenv
load_dotenv(ROOT / '.env')
VK_TOKEN = os.getenv('VK_TOKEN', '')
VK_GROUP_ID = os.getenv('VK_GROUP_ID', '497763452')

# ========== БД ==========
def init_db():
    """Инициализация БД."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS futures_positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            direction TEXT NOT NULL,  -- LONG / SHORT
            volume REAL NOT NULL DEFAULT 1.0,
            entry_score REAL,
            entry_time TEXT NOT NULL,
            entry_price REAL,
            entry_atr REAL,
            status TEXT DEFAULT 'OPEN',  -- OPEN / CLOSED
            exit_time TEXT,
            exit_score REAL,
            exit_price REAL,
            pnl REAL DEFAULT 0,
            exit_reason TEXT  -- SIGNAL / STOP / SCORE_EXIT
        )
    ''')
    conn.commit()
    conn.close()
    print("✅ БД инициализирована")

# ========== VK ==========
def send_vk_message(message):
    """Отправить сообщение в VK."""
    if not VK_TOKEN:
        print("❌ VK_TOKEN не настроен")
        return False
    try:
        import requests
        response = requests.post(
            'https://api.vk.com/method/messages.send',
            params={
                'access_token': VK_TOKEN,
                'peer_id': VK_GROUP_ID,
                'message': message,
                'random_id': int(datetime.now().timestamp() * 1000),
                'v': '5.131'
            }
        )
        return response.json().get('response', False)
    except Exception as e:
        print(f"❌ Ошибка отправки VK: {e}")
        return False

# ========== ОСНОВНЫЕ ФУНКЦИИ ==========
def get_open_positions():
    """Получить открытые позиции."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM futures_positions WHERE status = "OPEN"')
    positions = cursor.fetchall()
    conn.close()
    return positions

def open_position(ticker, direction, volume, score, price, atr):
    """Открыть позицию."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO futures_positions (ticker, direction, volume, entry_score, entry_time, entry_price, entry_atr)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (ticker, direction, volume, score, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), price, atr))
    conn.commit()
    conn.close()

    emoji = '🟢' if direction == 'LONG' else '🔴'
    message = f"🤖 ФЬЮЧЕРС-РОБОТ: {emoji} {direction} {ticker}: скор={score:.1f}, цена={price:.2f}"
    send_vk_message(message)
    print(f"✅ Открыта позиция: {message}")

def close_position(position_id, ticker, direction, exit_score, exit_price, reason):
    """Закрыть позицию."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Получаем параметры позиции
    cursor.execute('SELECT entry_price, entry_atr, volume FROM futures_positions WHERE id = ?', (position_id,))
    pos = cursor.fetchone()
    if not pos:
        conn.close()
        return
    
    entry_price, entry_atr, volume = pos
    
    # Расчёт PnL
    if direction == 'LONG':
        pnl = (exit_price - entry_price) * volume
    else:
        pnl = (entry_price - exit_price) * volume
    
    cursor.execute('''
        UPDATE futures_positions SET 
            status = "CLOSED", exit_time = ?, exit_score = ?, exit_price = ?, pnl = ?, exit_reason = ?
        WHERE id = ?
    ''', (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), exit_score, exit_price, pnl, reason, position_id))
    conn.commit()
    conn.close()

    emoji = '🟢' if pnl > 0 else '🔴'
    message = f"🤖 ФЬЮЧЕРС-РОБОТ: ЗАКРЫТИЕ {ticker}: PnL={pnl:+.2f}₽ ({reason}) {emoji}"
    send_vk_message(message)
    print(f"✅ Закрыта позиция: {message}")

# ========== ГЛАВНЫЙ ЦИКЛ ==========
def main():
    """Основная функция."""
    print("=" * 60)
    print("🤖 РОБОТ ФЬЮЧЕРСОВ |", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    print("=" * 60)
    
    init_db()
    
    # Получаем список фьючерсов из tickers_config
    futures_tickers = []
    try:
        with open(ROOT / 'FinLabPy' / 'DataCollectors' / 'tickers_config.json') as f:
            tickers_config = json.load(f)
        futures_tickers = tickers_config.get('futures', [])
    except Exception as e:
        print(f'Ошибка загрузки конфига: {e}')
        futures_tickers = []
    
    # Открытые позиции
    open_positions = get_open_positions()
    open_tickers = {pos[1] for pos in open_positions}  # ticker в колонке 1
    
    # Проверяем сигналы
    print(f'Проверяю {len(futures_tickers)} тикеров...')
    for ticker in futures_tickers[:10]:  # Пока первые 10 для теста
        print(f'  → {ticker}')
        try:
            # Загружаем данные
            d1_file = DATA_ROOT / 'candles' / f'{ticker}_D1.parquet'
            h4_file = DATA_ROOT / 'candles' / f'{ticker}_H4.parquet'
            h1_file = DATA_ROOT / 'candles' / f'{ticker}_H1.parquet'
            futoi_file = DATA_ROOT / 'futoi' / f'{ticker}_futoi.parquet'
            
            if not all([d1_file.exists(), h4_file.exists(), h1_file.exists()]):
                continue
            
            df_d1 = pd.read_parquet(d1_file)
            df_4h = pd.read_parquet(h4_file)
            df_1h = pd.read_parquet(h1_file)
            
            # Загружаем FutOI данные
            if futoi_file.exists():
                df_futoi = pd.read_parquet(futoi_file)
                if 'tradedate' in df_futoi.columns and 'clgroup' in df_futoi.columns:
                    df_futoi['tradedate'] = pd.to_datetime(df_futoi['tradedate'])
                    
                    # Считаем fiz_buy_ratio = % покупок физиков
                    fiz = df_futoi[df_futoi['clgroup'] == 'FIZ'].copy()
                    yur = df_futoi[df_futoi['clgroup'] == 'YUR'].copy()
                    
                    fiz['buy_ratio'] = fiz['pos_long'] / (fiz['pos_long'] + fiz['pos_short']).replace(0, 1) * 100
                    yur['buy_ratio'] = yur['pos_long'] / (yur['pos_long'] + yur['pos_short']).replace(0, 1) * 100
                    
                    # Нетто-позиции
                    fiz['phys_net'] = fiz['pos_long'] - fiz['pos_short']
                    yur['corp_net'] = yur['pos_long'] - yur['pos_short']
                    
                    # Агрегируем по дням
                    fiz_d1 = fiz.groupby('tradedate').agg({'buy_ratio': 'last', 'phys_net': 'last'}).rename(columns={'buy_ratio': 'fiz_buy_ratio'})
                    yur_d1 = yur.groupby('tradedate').agg({'buy_ratio': 'last', 'corp_net': 'last'}).rename(columns={'buy_ratio': 'yur_buy_ratio'})
                    
                    df_futoi_d1 = fiz_d1.join(yur_d1, on='tradedate')
                    df_futoi_d1 = df_futoi_d1.reset_index()
                    
                    # Объединяем со свечами
                    df_d1['begin'] = pd.to_datetime(df_d1['begin'])
                    df_d1 = pd.merge(df_d1, df_futoi_d1, left_on='begin', right_on='tradedate', how='left')
                    df_d1 = df_d1.ffill()
                    df_d1['fiz_buy_ratio'] = df_d1['fiz_buy_ratio'].fillna(50)
                    df_d1['phys_net'] = df_d1['phys_net'].fillna(0)
                    df_d1['corp_net'] = df_d1['corp_net'].fillna(0)
                else:
                    df_d1['fiz_buy_ratio'] = 50
                    df_d1['phys_net'] = 0
                    df_d1['corp_net'] = 0
            else:
                df_d1['fiz_buy_ratio'] = 50
                df_d1['phys_net'] = 0
                df_d1['corp_net'] = 0
            
            # Тренд D1
            trend_up = False
            trend_down = False
            if len(df_d1) >= 20:
                df_d1['sma20'] = df_d1['close'].rolling(20).mean()
                last_price = float(df_d1['close'].iloc[-1]) if not isinstance(df_d1['close'].iloc[-1], bytes) else 0
                sma20 = float(df_d1['sma20'].iloc[-1]) if not isinstance(df_d1['sma20'].iloc[-1], bytes) else 0
                if last_price > sma20 * 1.02:
                    trend_up = True
                elif last_price < sma20 * 0.98:
                    trend_down = True
            
            # Вердикт
            verdict = get_unified_scanner_verdict(
                df_d1, df_4h, df_1h,
                d1_trend_up=trend_up, d1_trend_down=trend_down,
                hi2_value=None, garch_vol=0,
                ofi=None, cum_delta=None,
                is_distribution=False, is_accumulation=False,
                hpi_signal=None, hpi_divergence=False,
                zweig_signal=None, volume_spike=False, rvi_val=None
            )
            
            decision = verdict.get('decision', 'WAIT')
            score = verdict.get('score', 0)
            crisis = verdict.get('crisis_mode', False)
            
            entry_threshold = CRISIS_ENTRY_SCORE if crisis else ENTRY_SCORE
            exit_threshold = CRISIS_EXIT_SCORE if crisis else EXIT_SCORE
            
            # ATR для стопа
            entry_price = float(df_1h['close'].iloc[-1]) if not isinstance(df_1h['close'].iloc[-1], bytes) else 0
            atr = 0
            if len(df_1h) >= 14:
                df_1h_copy = df_1h.copy()
                df_1h_copy['high'] = df_1h_copy['high'].apply(lambda x: float(x) if not isinstance(x, bytes) else 0)
                df_1h_copy['low'] = df_1h_copy['low'].apply(lambda x: float(x) if not isinstance(x, bytes) else 0)
                df_1h_copy['close'] = df_1h_copy['close'].apply(lambda x: float(x) if not isinstance(x, bytes) else 0)
                df_1h_copy['tr'] = np.maximum(
                    df_1h_copy['high'] - df_1h_copy['low'],
                    np.maximum(
                        abs(df_1h_copy['high'] - df_1h_copy['close'].shift(1)),
                        abs(df_1h_copy['low'] - df_1h_copy['close'].shift(1))
                    )
                )
                atr = float(df_1h_copy['tr'].rolling(14).mean().iloc[-1])
            
            if ticker in open_tickers:
                # Проверяем выход
                for pos in open_positions:
                    if pos[1] == ticker:
                        pos_id = pos[0]
                        pos_direction = pos[2]
                        pos_entry_price = pos[6] if len(pos) > 6 else 0
                        pos_atr = pos[7] if len(pos) > 7 else 0
                        
                        # Стоп-лосс
                        if pos_direction == 'LONG' and pos_atr > 0:
                            stop_price = pos_entry_price - pos_atr
                            if entry_price <= stop_price:
                                close_position(pos_id, ticker, pos_direction, score, entry_price, 'STOP')
                                open_tickers.discard(ticker)
                                break
                        elif pos_direction == 'SHORT' and pos_atr > 0:
                            stop_price = pos_entry_price + pos_atr
                            if entry_price >= stop_price:
                                close_position(pos_id, ticker, pos_direction, score, entry_price, 'STOP')
                                open_tickers.discard(ticker)
                                break
                        
                        # Обратный сигнал
                        if pos_direction == 'LONG' and decision == 'SHORT':
                            close_position(pos_id, ticker, pos_direction, score, entry_price, 'SIGNAL')
                            open_tickers.discard(ticker)
                            break
                        elif pos_direction == 'SHORT' and decision == 'LONG':
                            close_position(pos_id, ticker, pos_direction, score, entry_price, 'SIGNAL')
                            open_tickers.discard(ticker)
                            break
                        
                        # Низкий скор
                        if score < exit_threshold:
                            close_position(pos_id, ticker, pos_direction, score, entry_price, 'SCORE_EXIT')
                            open_tickers.discard(ticker)
                            break
            else:
                # Проверяем вход
                if decision == 'LONG' and score >= entry_threshold:
                    open_position(ticker, 'LONG', 1.0, score, entry_price, atr)
                    open_tickers.add(ticker)
                elif decision == 'SHORT' and score >= entry_threshold:
                    open_position(ticker, 'SHORT', 1.0, score, entry_price, atr)
                    open_tickers.add(ticker)
        
        except Exception as e:
            print(f"  ❌ {ticker}: {e}")
    
    print("\n✅ Проверка завершена")

if __name__ == '__main__':
    # Бесконечный цикл для systemd
    while True:
        main()
        print('Ожидание 1 час...')
        time.sleep(3600)  # Проверка каждый час
