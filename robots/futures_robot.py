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

# Максимум одновременных открытых позиций (контроль риска, принцип Саймонса)
MAX_POSITIONS = 10

# === СТОПЫ (15.09.2026) ===
STOP_ATR_MULT = 3.2   # начальный стоп: 3.2×ATR (default)
BE_MOVE_ATR = 1.5     # при движении в плюс на 1.5×ATR — стоп в безубыток

# Индивидуальные множители ATR по тикерам
def load_stop_config():
    cfg_file = ROOT / 'robots' / 'stop_config.json'
    if not cfg_file.exists():
        return {}
    try:
        import json
        with open(cfg_file) as f:
            cfg = json.load(f)
        return cfg.get('individual', {})
    except Exception as e:
        print(f"⚠️ Ошибка чтения stop_config.json: {e}")
        return {}

STOP_ATR_INDIVIDUAL = load_stop_config()

def get_stop_mult(ticker):
    """Получить множитель ATR для тикера."""
    return STOP_ATR_INDIVIDUAL.get(ticker, STOP_ATR_MULT)


# Cooldown после STOP по тикеру (часы) — защита от whipsaw
COOLDOWN_HOURS = 4

# ========== ПРОВЕРКА СВЕЖЕСТИ ==========
FRESHNESS_THRESHOLDS = {
    'M10': 2, 'H1': 4, 'H4': 25, 'D1': 25,
    'futoi': 24,
}


def is_moex_trading_day():
    """Проверить, что сегодня торговый день MOEX (упрощённо, 2026)."""
    from datetime import datetime as _dt
    now = _dt.now()
    no_trade_weekends = [
        (1,3),(1,4),(1,10),(1,11),(2,14),(2,15),(3,7),(3,8),
        (3,21),(3,22),(5,9),(5,10),(6,20),(6,21),(8,1),(8,2),
        (8,15),(8,16),(9,12),(9,13),(10,24),(10,25),(12,5),(12,6),
    ]
    no_trade_holidays = [
        (1,1),(1,2),(1,5),(1,6),(1,7),(1,8),(3,8),(5,9),(12,31),
    ]
    md = (now.month, now.day)
    if md in no_trade_weekends or md in no_trade_holidays:
        return False
    return True


def is_futoi_fresh(ticker):
    """Проверить свежесть FutOI. Возвращает (fresh: bool, age_hours: float|None)."""
    if not is_moex_trading_day():
        return True, 0.0

    # Вне торговых часов (до 10:00 или после 19:00 МСК) — не проверяем
    from datetime import datetime as _dt
    now_hour = _dt.now().hour
    if now_hour < 10 or now_hour >= 19:
        return True, 0.0

    futoi_file = DATA_ROOT / 'futoi' / f'{ticker}_futoi.parquet'
    if not futoi_file.exists():
        return False, None

    try:
        df = pd.read_parquet(futoi_file)
        if len(df) == 0:
            return False, None

        last_row = df.iloc[-1]

        last_dt = None
        if 'tradedate' in df.columns and 'tradetime' in df.columns:
            last_dt = pd.to_datetime(f"{last_row['tradedate']} {last_row['tradetime']}")
        elif 'tradedate' in df.columns and 'block' in df.columns:
            last_dt = pd.to_datetime(f"{last_row['tradedate']} {last_row['block']}")
        elif 'tradedate' in df.columns:
            last_dt = pd.to_datetime(last_row['tradedate'])
        elif 'begin' in df.columns:
            last_dt = pd.to_datetime(last_row['begin'])

        if last_dt is None:
            print(f"  ⚠️ {ticker}: нет колонки с датой")
            return False, None

        if last_dt.tzinfo is not None:
            last_dt = last_dt.tz_localize(None)

        age_hours = (pd.Timestamp.now() - last_dt).total_seconds() / 3600
        return age_hours <= FRESHNESS_THRESHOLDS['futoi'], age_hours

    except Exception as e:
        print(f"  ⚠️ {ticker}: ошибка проверки FutOI: {e}")
        return False, None

def get_hi2_for_ticker(ticker):
    """Получить 11 метрик HI2 для тикера. Возвращает dict или None."""
    hi2_file = DATA_ROOT / 'hi2_daily.parquet'
    if not hi2_file.exists():
        return None
    
    try:
        df = pd.read_parquet(hi2_file)
        if len(df) == 0:
            return None
        
        # Фильтруем по тикеру
        df_t = df[df['ticker'] == ticker]
        if len(df_t) == 0:
            return None
        
        # Берём последнюю строку
        last = df_t.iloc[-1]
        
        return {
            'hhi_agressive': float(last.get('hhi_agressive', 0)) if pd.notna(last.get('hhi_agressive')) else None,
            'hhi_agressive_buy': float(last.get('hhi_agressive_buy', 0)) if pd.notna(last.get('hhi_agressive_buy')) else None,
            'hhi_agressive_sell': float(last.get('hhi_agressive_sell', 0)) if pd.notna(last.get('hhi_agressive_sell')) else None,
            'hhi_buy': float(last.get('hhi_buy', 0)) if pd.notna(last.get('hhi_buy')) else None,
            'hhi_sell': float(last.get('hhi_sell', 0)) if pd.notna(last.get('hhi_sell')) else None,
            'hhi_netflow_buy': float(last.get('hhi_netflow_buy', 0)) if pd.notna(last.get('hhi_netflow_buy')) else None,
            'hhi_netflow_sell': float(last.get('hhi_netflow_sell', 0)) if pd.notna(last.get('hhi_netflow_sell')) else None,
            'hhi_passive': float(last.get('hhi_passive', 0)) if pd.notna(last.get('hhi_passive')) else None,
            'hhi_passive_buy': float(last.get('hhi_passive_buy', 0)) if pd.notna(last.get('hhi_passive_buy')) else None,
            'hhi_passive_sell': float(last.get('hhi_passive_sell', 0)) if pd.notna(last.get('hhi_passive_sell')) else None,
            'hhi_volume': float(last.get('hhi_volume', 0)) if pd.notna(last.get('hhi_volume')) else None,
        }
    except Exception as e:
        print(f"  ⚠️ {ticker}: ошибка чтения HI2: {e}")
        return None


def get_disb_for_ticker(ticker):
    """Получить значение disb (TradeStats) для тикера. Возвращает float или None."""
    ts_file = DATA_ROOT / 'tradestats' / f'{ticker}_tradestats.parquet'
    if not ts_file.exists():
        return None
    
    try:
        df = pd.read_parquet(ts_file)
        if len(df) == 0:
            return None
        
        # Берём последнюю строку
        last = df.iloc[-1]
        disb_val = last.get('disb')
        if pd.isna(disb_val):
            return None
        return float(disb_val)
    except Exception as e:
        print(f"  ⚠️ {ticker}: ошибка чтения TradeStats: {e}")
        return None



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

    # Начальный стоп — 3.2×ATR
    if direction == 'LONG':
        stop_price = price - atr * STOP_ATR_MULT
    else:
        stop_price = price + atr * STOP_ATR_MULT

    cursor.execute('''
        INSERT INTO futures_positions (ticker, direction, volume, entry_score, entry_time, entry_price, entry_atr, stop_price)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (ticker, direction, volume, score, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), price, atr, stop_price))
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
        pnl_points = (exit_price - entry_price) * volume
    else:
        pnl = (entry_price - exit_price) * point_value * volume
        pnl_points = (entry_price - exit_price) * volume
    
    cursor.execute('''
        UPDATE futures_positions SET 
            status = "CLOSED", exit_time = ?, exit_score = ?, exit_price = ?, pnl = ?, pnl_points = ?, point_value = ?, exit_reason = ?
        WHERE id = ?
    ''', (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), exit_score, exit_price,
          pnl, pnl_points, point_value, reason, position_id))
    conn.commit()
    conn.close()

    emoji = '🟢' if pnl > 0 else '🔴'
    message = f"🤖 ФЬЮЧЕРС-РОБОТ: ЗАКРЫТИЕ {ticker}: PnL={pnl:+.2f}₽ ({reason}) {emoji}"
    send_vk_message(message)
    print(f"✅ Закрыта позиция: {message}")

# ========== ГЛАВНЫЙ ЦИКЛ ==========

def check_expiry():
    """Проверить приближающиеся экспирации. Закрывать за N дней."""
    if not is_moex_trading_day():
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, ticker, direction, entry_price, volume, expiry_date
        FROM futures_positions
        WHERE status='OPEN' AND expiry_date IS NOT NULL
    """)
    positions = cursor.fetchall()
    conn.close()

    now = pd.Timestamp.now()

    for pos in positions:
        pid, ticker, direction, entry_price, volume, expiry_date = pos
        try:
            expiry = pd.to_datetime(expiry_date)
            days_left = (expiry - now).days

            # Закрываем за 2 дня до экспирации
            if days_left <= 2:
                # Получить текущую цену (M10 close)
                try:
                    df = pd.read_parquet(DATA_ROOT / 'candles' / f'{ticker}_M10.parquet')
                    exit_price = float(df.iloc[-1]['close'])
                except Exception:
                    continue

                print(f'  ⏰ {ticker}: экспирация через {days_left} дн. — ЗАКРЫВАЕМ')
                close_position(pid, ticker, direction, 0, exit_price, 'EXPIRY')
        except Exception as e:
            print(f'  ⚠️ check_expiry({ticker}): {e}')


def check_stops_only():
    """Быстрая проверка стопов по M10 (high/low) — каждые 10 минут."""
    # В неторговые дни M10 не обновляются — проверка бессмысленна
    if not is_moex_trading_day():
        return
    
    open_positions = get_open_positions()
    if not open_positions:
        return
    
    conn = sqlite3.connect(DB_PATH)  # для обновления stop_price
    cursor = conn.cursor()

    closed_count = 0
    for pos in open_positions:
        pos_id = pos[0]
        ticker = pos[1]
        direction = pos[2]
        entry_price = pos[6] if len(pos) > 6 else 0
        entry_atr = pos[7] if len(pos) > 7 else 0
        
        if not entry_atr or entry_atr <= 0:
            continue
        
        # Загружаем M10
        m10_file = DATA_ROOT / 'candles' / f'{ticker}_M10.parquet'
        if not m10_file.exists():
            continue
        
        try:
            df = pd.read_parquet(m10_file)
            if len(df) == 0:
                continue
            last = df.iloc[-1]
            low = float(last['low']) if not isinstance(last['low'], bytes) else 0
            high = float(last['high']) if not isinstance(last['high'], bytes) else 0
            
            # === Стоп 3.2×ATR + безубыток (15.09.2026) ===
            # Загружаем текущий stop_price из БД
            cursor.execute('SELECT stop_price FROM futures_positions WHERE id = ?', (pos_id,))
            sp_row = cursor.fetchone()
            current_stop = sp_row[0] if sp_row and sp_row[0] is not None else None

            if direction == 'LONG':
                # Начальный стоп — 3.2×ATR
                if current_stop is None:
                    stop_price = entry_price - entry_atr * STOP_ATR_MULT
                else:
                    stop_price = current_stop

                # Проверяем, не пора ли в безубыток
                if high >= entry_price + entry_atr * BE_MOVE_ATR:
                    if stop_price < entry_price:
                        stop_price = entry_price
                        cursor.execute('UPDATE futures_positions SET stop_price = ? WHERE id = ?', (stop_price, pos_id))
                        conn.commit()
                        print(f'🔒 {ticker}: стоп в безубыток ({stop_price:.2f})')

                # Проверяем стоп
                if low <= stop_price:
                    reason = 'BREAKEVEN' if stop_price == entry_price else 'STOP'
                    close_position(pos_id, ticker, direction, 0, stop_price, reason)
                    print(f'🛑 {ticker}: {reason} по {stop_price:.2f} (low={low:.2f})')
                    closed_count += 1

            elif direction == 'SHORT':
                # Начальный стоп — 3.2×ATR
                if current_stop is None:
                    stop_price = entry_price + entry_atr * STOP_ATR_MULT
                else:
                    stop_price = current_stop

                # Проверяем, не пора ли в безубыток
                if low <= entry_price - entry_atr * BE_MOVE_ATR:
                    if stop_price > entry_price:
                        stop_price = entry_price
                        cursor.execute('UPDATE futures_positions SET stop_price = ? WHERE id = ?', (stop_price, pos_id))
                        conn.commit()
                        print(f'🔒 {ticker}: стоп в безубыток ({stop_price:.2f})')

                # Проверяем стоп
                if high >= stop_price:
                    reason = 'BREAKEVEN' if stop_price == entry_price else 'STOP'
                    close_position(pos_id, ticker, direction, 0, stop_price, reason)
                    print(f'🛑 {ticker}: {reason} по {stop_price:.2f} (high={high:.2f})')
                    closed_count += 1
        except Exception as e:
            print(f'  ❌ {ticker}: {e}')
    
    conn.close()

    if closed_count:
        print(f'  ✅ Закрыто по стопам: {closed_count}')


def is_in_cooldown(ticker):
    """Проверить, был ли STOP по тикеру за последние COOLDOWN_HOURS."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cutoff = (datetime.now() - timedelta(hours=COOLDOWN_HOURS)).strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute("""
        SELECT COUNT(*) FROM futures_positions
        WHERE ticker = ? AND status = 'CLOSED'
        AND exit_reason = 'STOP' AND exit_time > ?
    """, (ticker, cutoff))
    count = cursor.fetchone()[0]
    conn.close()
    return count > 0


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

                # Merge со свечами 4H по 'block' (15.09.2026 fix)
                # block в свечах = '11:00', в futoi = '2026-09-14 11:00:00'
                # Собираем полный datetime: tradedate + block
                df_4h['dt_full'] = pd.to_datetime(df_4h['tradedate'].astype(str) + ' ' + df_4h['block'].astype(str))
                df_futoi_4h['dt_full'] = pd.to_datetime(df_futoi_4h['hour'])
                
                # Merge по ближайшему часу (asof)
                df_4h = pd.merge_asof(
                    df_4h.sort_values('dt_full'),
                    df_futoi_4h[['dt_full', 'fiz_buy_ratio', 'fiz_ratio_delta', 'yur_buy_ratio']].sort_values('dt_full'),
                    on='dt_full',
                    direction='backward'
                )
                df_4h = df_4h.ffill()
                df_4h['fiz_buy_ratio'] = df_4h['fiz_buy_ratio'].fillna(50)

                # Merge со свечами 1H по 'hour' (15.09.2026 fix)
                df_1h['dt_full'] = pd.to_datetime(df_1h['begin'])
                df_futoi_1h['dt_full'] = pd.to_datetime(df_futoi_1h['hour'])
                
                df_1h = pd.merge_asof(
                    df_1h.sort_values('dt_full'),
                    df_futoi_1h[['dt_full', 'fiz_buy_ratio', 'fiz_ratio_delta', 'yur_buy_ratio']].sort_values('dt_full'),
                    on='dt_full',
                    direction='backward'
                )
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
            
            # Читаем HI2 для тикера (11 метрик)
            hi2_data = get_hi2_for_ticker(ticker)
            # Читаем TradeStats disb
            disb_val = get_disb_for_ticker(ticker)
            if hi2_data:
                hi2_value = hi2_data.get('hhi_agressive')
            else:
                hi2_value = None

            # Вердикт
            verdict = get_unified_scanner_verdict(
                df_d1, df_4h, df_1h,
                d1_trend_up=trend_up, d1_trend_down=trend_down,
                hi2_value=hi2_value, garch_vol=0,
                hi2_agressive_buy=hi2_data.get('hhi_agressive_buy') if hi2_data else None,
                hi2_agressive_sell=hi2_data.get('hhi_agressive_sell') if hi2_data else None,
                hi2_buy=hi2_data.get('hhi_buy') if hi2_data else None,
                hi2_sell=hi2_data.get('hhi_sell') if hi2_data else None,
                hi2_netflow_buy=hi2_data.get('hhi_netflow_buy') if hi2_data else None,
                hi2_netflow_sell=hi2_data.get('hhi_netflow_sell') if hi2_data else None,
                hi2_passive=hi2_data.get('hhi_passive') if hi2_data else None,
                hi2_passive_buy=hi2_data.get('hhi_passive_buy') if hi2_data else None,
                hi2_passive_sell=hi2_data.get('hhi_passive_sell') if hi2_data else None,
                hi2_volume=hi2_data.get('hhi_volume') if hi2_data else None,
                disb=disb_val,
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
                        
                        # Стоп-лосс проверяется в check_stops_only() каждые 10 мин
                        # Здесь — только обратный сигнал
                        
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
                    # Проверка лимита позиций (контроль риска)
                    if len(open_positions) >= MAX_POSITIONS:
                        print(f'  ⚠️ {ticker}: лимит позиций ({MAX_POSITIONS}) — не открываем')
                        continue
                    
                    # Проверка cooldown после STOP
                    if is_in_cooldown(ticker):
                        print(f'  ⏸️ {ticker}: cooldown после STOP ({COOLDOWN_HOURS}ч)')
                        continue
                    
                    if decision == 'LONG' and score >= entry_threshold:
                        open_position(ticker, 'LONG', 1.0, score, entry_price, atr)
                        open_tickers.add(ticker)
                        open_positions.append((None, ticker, 'LONG'))
                    elif decision == 'SHORT' and score >= entry_threshold:
                        open_position(ticker, 'SHORT', 1.0, score, entry_price, atr)
                        open_tickers.add(ticker)
                        open_positions.append((None, ticker, 'SHORT'))
        
        except Exception as e:
            print(f"  ❌ {ticker}: {e}")
    
    print("\n✅ Проверка завершена")

if __name__ == '__main__':
    # Бесконечный цикл для systemd
    while True:
        main()
        print('Ожидание 1 час (стопы проверяются каждые 10 мин)...')
        
        # Проверка стопов каждые 10 минут (6 раз по 600 сек = 1 час)
        for i in range(6):
            time.sleep(600)
            check_stops_only()
            check_expiry()
            print(f'  [{i+1}/6] Проверка стопов завершена')
