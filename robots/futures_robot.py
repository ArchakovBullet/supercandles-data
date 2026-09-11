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

# Загружаем справочник стоимости пункта
CONTRACT_POINTS_PATH = ROOT / 'robots' / 'contract_points.json'
try:
    with open(CONTRACT_POINTS_PATH, 'r') as _f:
        CONTRACT_POINTS = json.load(_f)
except Exception:
    CONTRACT_POINTS = {}
STATE_FILE = ROOT / 'robots' / 'futures_robot_state.json'
COMMAND_FILE = ROOT / 'robots' / 'futures_robot_command.txt'

# Пороги
ENTRY_SCORE = 60
EXIT_SCORE = 40
CRISIS_ENTRY_SCORE = 80
CRISIS_EXIT_SCORE = 40

# ========== ПРОВЕРКА СВЕЖЕСТИ ==========
FRESHNESS_THRESHOLDS = {
    'M10': 2, 'H1': 4, 'H4': 12, 'D1': 24,
    'futoi': 24,
}

def is_futoi_fresh(ticker):
    """Проверить свежесть FutOI. Возвращает (fresh: bool, age_hours: float|None)."""
    futoi_file = DATA_ROOT / 'futoi' / f'{ticker}_futoi.parquet'
    if not futoi_file.exists():
        return False, None
    try:
        df = pd.read_parquet(futoi_file, columns=['tradedate', 'tradetime'])
        last_row = df.iloc[-1]
        last_dt = pd.to_datetime(f"{last_row['tradedate']} {last_row['tradetime']}")
        age_hours = (pd.Timestamp.now() - last_dt).total_seconds() / 3600
        return age_hours <= FRESHNESS_THRESHOLDS['futoi'], age_hours
    except Exception as e:
        print(f"  \u26a0\ufe0f {ticker}: \u043e\u0448\u0438\u0431\u043a\u0430 \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0438 FutOI: {e}")
        return False, None

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
    
    # Расчёт PnL с учётом стоимости пункта
    point_value = CONTRACT_POINTS.get(ticker, 1.0)
    if direction == 'LONG':
        pnl = (exit_price - entry_price) * point_value * volume
    else:
        pnl = (entry_price - exit_price) * point_value * volume
    
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
    # Фильтруем: только те, у кого есть все 4 файла (D1, H4, H1, FutOI)
    ready_tickers = []
    for t in futures_tickers:
        if ((DATA_ROOT / 'candles' / f'{t}_D1.parquet').exists() and
            (DATA_ROOT / 'candles' / f'{t}_H4.parquet').exists() and
            (DATA_ROOT / 'candles' / f'{t}_H1.parquet').exists() and
            (DATA_ROOT / 'futoi' / f'{t}_futoi.parquet').exists()):
            ready_tickers.append(t)

    print(f'Проверяю {len(ready_tickers)} тикеров (из {len(futures_tickers)})...')
    for ticker in ready_tickers:
        print(f'  → {ticker}')
        try:
            # Проверка свежести FutOI
            futoi_fresh, futoi_age = is_futoi_fresh(ticker)
            if not futoi_fresh:
                age_str = f'{futoi_age:.1f}ч' if futoi_age else 'нет данных'
                print(f'    ⚠️ FutOI устарел ({age_str}) — новые позиции не открываем')
                # Открытые позиции не закрываем — ждут восстановления
                continue

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
            
            # Загружаем FutOI из готовых агрегатов (без самодельной агрегации)
            futoi_4h_file = DATA_ROOT / 'futoi_4h' / 'futoi_4h.parquet'
            futoi_1h_file = DATA_ROOT / 'futoi_1h' / 'futoi_1h.parquet'

            if futoi_4h_file.exists() and futoi_1h_file.exists():
                df_futoi_4h_all = pd.read_parquet(futoi_4h_file)
                df_futoi_1h_all = pd.read_parquet(futoi_1h_file)

                # Фильтруем по тикеру
                df_futoi_4h = df_futoi_4h_all[df_futoi_4h_all['ticker'] == ticker].copy()
                df_futoi_1h = df_futoi_1h_all[df_futoi_1h_all['ticker'] == ticker].copy()

                # Merge со свечами 4H по 'hour'
                df_4h['tradedate'] = pd.to_datetime(df_4h['tradedate'])
                df_futoi_4h['hour'] = pd.to_datetime(df_futoi_4h['hour'])
                df_4h = pd.merge(df_4h, df_futoi_4h[['hour', 'fiz_buy_ratio', 'fiz_ratio_delta']],
                                 left_on='tradedate', right_on='hour', how='left')
                df_4h = df_4h.ffill()
                df_4h['fiz_buy_ratio'] = df_4h['fiz_buy_ratio'].fillna(50)

                # Merge со свечами 1H по 'hour'
                df_1h['tradedate'] = pd.to_datetime(df_1h['begin'])
                df_futoi_1h['hour'] = pd.to_datetime(df_futoi_1h['hour'])
                df_1h = pd.merge(df_1h, df_futoi_1h[['hour', 'fiz_buy_ratio', 'fiz_ratio_delta']],
                                 left_on='tradedate', right_on='hour', how='left')
                df_1h = df_1h.ffill()
                df_1h['fiz_buy_ratio'] = df_1h['fiz_buy_ratio'].fillna(50)

                # Для D1 берём последнее значение из 4H (агрегация по дню)
                df_futoi_4h['tradedate_only'] = df_futoi_4h['hour'].dt.date
                df_d1_futoi = df_futoi_4h.groupby('tradedate_only').agg({'fiz_buy_ratio': 'last'}).reset_index()
                df_d1['begin'] = pd.to_datetime(df_d1['begin'])
                df_d1['tradedate_only'] = df_d1['begin'].dt.date
                df_d1 = pd.merge(df_d1, df_d1_futoi, on='tradedate_only', how='left')
                df_d1 = df_d1.ffill()
                df_d1['fiz_buy_ratio'] = df_d1['fiz_buy_ratio'].fillna(50)
            else:
                # Fallback: если файлов нет — нейтральные значения
                df_d1['fiz_buy_ratio'] = 50
                df_4h['fiz_buy_ratio'] = 50
                df_1h['fiz_buy_ratio'] = 50

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
                            stop_price = pos_entry_price - pos_atr * 2
                            if entry_price <= stop_price:
                                close_position(pos_id, ticker, pos_direction, score, entry_price, 'STOP')
                                open_tickers.discard(ticker)
                                break
                        elif pos_direction == 'SHORT' and pos_atr > 0:
                            stop_price = pos_entry_price + pos_atr * 2
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
                # Фильтр времени: не входить до 10:00 и после 18:00 МСК
                import datetime as _dt
                _now_msk = _dt.datetime.now(_dt.timezone(_dt.timedelta(hours=3)))
                _hour = _now_msk.hour
                _is_trading_time = (10 <= _hour < 18)

                # Проверяем вход
                if _is_trading_time:
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
