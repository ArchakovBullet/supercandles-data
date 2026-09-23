"""
Торговый робот акций (бумажный режим)
===================================================
Логика:
- D1 (стратегия) + H1 (тактика) + M10 (точка входа)
- Вход: decision == 'LONG' и score >= 60 (70 при Zweig CAUTION)
- Выход: decision == 'SHORT' или стоп/безубыток
- Стоп: 3.2×ATR + безубыток ×1.001
- Только LONG (шорт по акциям запрещён)
- Макро-фильтры: TRIN, RVI, режим рынка, сессия, Zweig
- Сектор: stock_to_sector.json (MOEX ISS + HARDCODED)
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

sys.path.insert(0, '/root/finlab/FinLabPy')

from dotenv import load_dotenv
from My_Indicators.stock_scanner_tf import get_stock_scanner_verdict
from My_Indicators.stock_screener import calculate_adx, calculate_choppiness
from My_Indicators.garch_indicator import calculate_garch_for_ticker
from My_Indicators.arms_index import calculate_trin
from My_Indicators.market_regime import get_market_regime
from My_Indicators.trading_session import get_session_status
from My_Indicators.zweig_filter import get_zweig_signal
from My_Indicators.sector_analysis import analyze_vs_sector

# ========== КОНФИГ ==========
ROOT = Path('/root/finlab')
DATA_ROOT = ROOT / 'data'
DB_PATH = ROOT / 'robots' / 'stocks_robot.db'
SECTOR_MAP_PATH = ROOT / 'robots' / 'stock_to_sector.json'

load_dotenv(ROOT / '.env')
VK_TOKEN = os.getenv('VK_TOKEN', '')
VK_GROUP_ID = os.getenv('VK_GROUP_ID', '497763452')

# Загружаем список акций
TICKERS_CONFIG_PATH = ROOT / 'FinLabPy' / 'DataCollectors' / 'tickers_config.json'
try:
    with open(TICKERS_CONFIG_PATH) as _f:
        _cfg = json.load(_f)
    STOCKS = _cfg.get('stocks', [])[:50]
except Exception as _e:
    print(f'⚠️ tickers_config.json: {_e}')
    STOCKS = []

# Загружаем мапу секторов
try:
    with open(SECTOR_MAP_PATH) as _f:
        _smap = json.load(_f)
    SECTOR_MAP = _smap.get('sectors', {})
    print(f'✅ Секторов загружено: {len(SECTOR_MAP)}')
except Exception as _e:
    print(f'⚠️ stock_to_sector.json: {_e}')
    SECTOR_MAP = {}

# ========== КОНСТАНТЫ ==========
MAX_POSITIONS = 10
STOP_ATR_MULT = 3.2
BE_MOVE_ATR = 1.5
BE_TARGET_MULT = 1.002
BE_EPS = 0.002
COOLDOWN_HOURS = 4
DEPOSIT = 100000
CHECK_INTERVAL = 3600
STOP_CHECK_INTERVAL = 600
ENTRY_SCORE_THRESHOLD = 60
ENTRY_SCORE_CAUTION = 70

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
            },
            timeout=10
        )
        return response.json().get('response', False)
    except Exception as e:
        print(f"❌ Ошибка отправки VK: {e}")
        return False

# ========== ПРОВЕРКА ДНЯ ==========
def is_moex_trading_day():
    """Проверить, что сегодня торговый день MOEX."""
    from datetime import datetime as _dt
    now = _dt.now()
    if now.weekday() >= 5:
        return False
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


def is_trading_time():
    """Проверить торговое время (10:00-18:00 МСК)."""
    import datetime as _dt
    _now_msk = _dt.datetime.now(_dt.timezone(_dt.timedelta(hours=3)))
    _hour = _now_msk.hour
    return (10 <= _hour < 18)

# ========== БД ==========
def init_db():
    """Инициализировать БД."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stock_positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            direction TEXT DEFAULT 'LONG',
            volume REAL DEFAULT 1.0,
            entry_price REAL,
            entry_atr REAL,
            stop_price REAL,
            entry_score REAL,
            entry_time TEXT,
            status TEXT DEFAULT 'OPEN',
            exit_price REAL,
            exit_time TEXT,
            exit_reason TEXT,
            pnl REAL,
            point_value REAL DEFAULT 1.0
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_ticker ON stock_positions(ticker)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_status ON stock_positions(status)')
    conn.commit()
    conn.close()


def get_open_positions():
    """Получить открытые позиции."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM stock_positions WHERE status = "OPEN"')
    positions = cursor.fetchall()
    conn.close()
    return positions


def is_in_cooldown(ticker):
    """Проверить, был ли STOP по тикеру за последние COOLDOWN_HOURS."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cutoff = (datetime.now() - timedelta(hours=COOLDOWN_HOURS)).strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute("""
        SELECT COUNT(*) FROM stock_positions
        WHERE ticker = ? AND status = 'CLOSED'
          AND exit_reason IN ('STOP', 'BREAKEVEN')
          AND exit_time >= ?
    """, (ticker, cutoff))
    count = cursor.fetchone()[0]
    conn.close()
    return count > 0


def open_position(ticker, score, price, atr):
    """Открыть позицию (LONG)."""
    if not is_moex_trading_day():
        print(f'  ⏸️ {ticker}: неторговый день — позиция не открывается')
        return
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    stop_price = price - atr * STOP_ATR_MULT

    cursor.execute('''
        INSERT INTO stock_positions (ticker, direction, volume, entry_score, entry_time, entry_price, entry_atr, stop_price)
        VALUES (?, 'LONG', 1.0, ?, ?, ?, ?, ?)
    ''', (ticker, score, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), price, atr, stop_price))
    conn.commit()
    conn.close()

    message = f"🤖 РОБОТ АКЦИЙ: 🟢 LONG {ticker}: скор={score:.1f}, цена={price:.2f}"
    send_vk_message(message)
    print(f"✅ Открыта позиция: {message}")


def close_position(position_id, ticker, exit_price, reason):
    """Закрыть позицию."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('SELECT entry_price, entry_atr, volume FROM stock_positions WHERE id = ?', (position_id,))
    pos = cursor.fetchone()
    if not pos:
        conn.close()
        return

    entry_price, entry_atr, volume = pos

    pnl = (exit_price - entry_price) * volume

    cursor.execute('''
        UPDATE stock_positions SET
            status = 'CLOSED', exit_time = ?, exit_price = ?, pnl = ?, exit_reason = ?
        WHERE id = ?
    ''', (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), exit_price, pnl, reason, position_id))
    conn.commit()
    conn.close()

    emoji = '🟢' if pnl > 0 else '🔴'
    message = f"🤖 РОБОТ АКЦИЙ: ЗАКРЫТИЕ {ticker}: PnL={pnl:+.2f}₽ ({reason}) {emoji}"
    send_vk_message(message)
    print(f"✅ Закрыта позиция: {message}")


def check_stops_only():
    """Проверка стопов по M10 (high/low)."""
    if not is_moex_trading_day():
        return

    open_positions = get_open_positions()
    if not open_positions:
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    closed_count = 0
    for pos in open_positions:
        pos_id = pos[0]
        ticker = pos[1]
        entry_price = pos[4]
        entry_atr = pos[5]

        if not entry_atr or entry_atr <= 0:
            continue

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

            cursor.execute('SELECT stop_price FROM stock_positions WHERE id = ?', (pos_id,))
            sp_row = cursor.fetchone()
            current_stop = sp_row[0] if sp_row and sp_row[0] is not None else None

            if current_stop is None:
                stop_price = entry_price - entry_atr * STOP_ATR_MULT
            else:
                stop_price = current_stop

            _be_target = entry_price * BE_TARGET_MULT
            if high >= entry_price + entry_atr * BE_MOVE_ATR:
                if stop_price < _be_target:
                    stop_price = _be_target
                    cursor.execute('UPDATE stock_positions SET stop_price = ? WHERE id = ?', (stop_price, pos_id))
                    conn.commit()
                    print(f'🔒 {ticker}: стоп в безубыток+комиссия ({stop_price:.2f})')

            if low <= stop_price:
                _be_eps = entry_price * BE_EPS
                _is_breakeven = abs(stop_price - entry_price) < _be_eps
                reason = 'BREAKEVEN' if _is_breakeven else 'STOP'
                close_position(pos_id, ticker, stop_price, reason)
                print(f'🛑 {ticker}: {reason} по {stop_price:.2f} (low={low:.2f})')
                closed_count += 1
        except Exception as e:
            print(f'  ❌ {ticker}: {e}')

    conn.close()

    if closed_count:
        print(f'  ✅ Закрыто по стопам: {closed_count}')

# ========== МАКРО-ФИЛЬТРЫ ==========
def read_rvi():
    """Прочитать RVI (индекс волатильности)."""
    rvi_file = DATA_ROOT / 'sector_indices' / 'RVI_D1.parquet'
    if not rvi_file.exists():
        return 15.0
    try:
        df = pd.read_parquet(rvi_file)
        return float(df['close'].iloc[-1]) if len(df) > 0 else 15.0
    except Exception:
        return 15.0


def calc_imoex_trend():
    """Тренд IMOEX (UP/DOWN/FLAT)."""
    imoex_file = DATA_ROOT / 'sector_indices' / 'IMOEX_D1.parquet'
    if not imoex_file.exists():
        return None
    try:
        df = pd.read_parquet(imoex_file)
        if len(df) < 20:
            return None
        df['sma20'] = df['close'].rolling(20).mean()
        last = df['close'].iloc[-1]
        sma = df['sma20'].iloc[-1]
        if last > sma * 1.02:
            return 'UP'
        elif last < sma * 0.98:
            return 'DOWN'
        return 'FLAT'
    except Exception:
        return None


def calc_rgbi_change():
    """Изменение RGBI за 5 дней (%)."""
    rgbi_file = DATA_ROOT / 'sector_indices' / 'RGBI_D1.parquet'
    if not rgbi_file.exists():
        return 0.0
    try:
        df = pd.read_parquet(rgbi_file)
        if len(df) < 5:
            return 0.0
        return (df['close'].iloc[-1] - df['close'].iloc[-5]) / df['close'].iloc[-5] * 100
    except Exception:
        return 0.0


def calc_avg_sector_change():
    """Среднее изменение секторов за 5 дней (%)."""
    sectors = ['MOEXMM', 'MOEXFN', 'MOEXOG', 'MOEXEU', 'MOEXTL']
    total = 0.0
    count = 0
    for s in sectors:
        f = DATA_ROOT / 'sector_indices' / f'{s}_D1.parquet'
        if not f.exists():
            continue
        try:
            df = pd.read_parquet(f)
            if len(df) >= 5:
                total += (df['close'].iloc[-1] - df['close'].iloc[-5]) / df['close'].iloc[-5] * 100
                count += 1
        except Exception:
            pass
    return total / count if count > 0 else 0.0


def calc_avg_adx_chop(tickers):
    """Средние ADX/Chop по списку акций (первые 10)."""
    adx_list = []
    chop_list = []
    for t in tickers[:10]:
        f = DATA_ROOT / 'candles' / f'{t}_D1.parquet'
        if not f.exists():
            continue
        try:
            df = pd.read_parquet(f)
            if len(df) < 30:
                continue
            adx_list.append(calculate_adx(df).iloc[-1])
            chop_list.append(calculate_choppiness(df).iloc[-1])
        except Exception:
            pass
    avg_adx = sum(adx_list) / len(adx_list) if adx_list else 0
    avg_chop = sum(chop_list) / len(chop_list) if chop_list else 50
    return avg_adx, avg_chop


def get_macro_filters():
    """Получить макро-фильтры (TRIN, RVI, режим, сессия, Zweig)."""
    # TRIN по 138 акциям
    try:
        _cfg_all = json.load(open(TICKERS_CONFIG_PATH))
        _all_stocks = _cfg_all.get('stocks', [])
    except Exception:
        _all_stocks = STOCKS
    trin = calculate_trin(tickers=_all_stocks)

    rvi = read_rvi()
    avg_adx, avg_chop = calc_avg_adx_chop(STOCKS)
    df_idx = pd.DataFrame({'adx': [avg_adx], 'choppiness': [avg_chop]})

    regime = get_market_regime(
        df_indices=df_idx,
        garch_vol=rvi,
        rvi_val=rvi,
        imoex_trend=calc_imoex_trend(),
        rgbi_change=calc_rgbi_change(),
        avg_sector_change=calc_avg_sector_change()
    )
    session = get_session_status()
    zweig = get_zweig_signal(regime, trin['trin'], session, rvi)

    return {
        'trin': trin,
        'rvi': rvi,
        'regime': regime,
        'session': session,
        'zweig': zweig,
        'avg_adx': avg_adx,
        'avg_chop': avg_chop,
    }


def get_hi2_for_ticker(ticker):
    """Получить 11 метрик HI2 для тикера."""
    hi2_file = DATA_ROOT / 'hi2_daily.parquet'
    if not hi2_file.exists():
        return None
    try:
        df = pd.read_parquet(hi2_file)
        if len(df) == 0:
            return None
        df_t = df[df['ticker'] == ticker]
        if len(df_t) == 0:
            return None
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


def get_sector_for(ticker, df_d1):
    """Получить sector_trend и relative_strength для тикера."""
    if ticker not in SECTOR_MAP:
        return {'sector_trend': None, 'relative_strength': 1.0}
    sector_name = SECTOR_MAP[ticker]
    sector_file = DATA_ROOT / 'sector_indices' / f'{sector_name}_D1.parquet'
    if not sector_file.exists():
        return {'sector_trend': None, 'relative_strength': 1.0}
    try:
        df_sec = pd.read_parquet(sector_file)
        result = analyze_vs_sector(df_d1, df_sec)
        if result:
            return {
                'sector_trend': result.get('sector_trend'),
                'relative_strength': result.get('relative_strength', 1.0),
            }
    except Exception as e:
        print(f'  ⚠️ {ticker}: ошибка сектора: {e}')
    return {'sector_trend': None, 'relative_strength': 1.0}


def calc_atr(df, period=14):
    """Рассчитать ATR."""
    high = df['high'].apply(lambda x: float(x) if not isinstance(x, bytes) else 0)
    low = df['low'].apply(lambda x: float(x) if not isinstance(x, bytes) else 0)
    close = df['close'].apply(lambda x: float(x) if not isinstance(x, bytes) else 0)
    tr = pd.DataFrame({
        'h_l': high - low,
        'h_c': abs(high - close.shift()),
        'l_c': abs(low - close.shift())
    }).max(axis=1)
    return float(tr.rolling(period).mean().iloc[-1])


def calc_atr_pct(df, period=14):
    """ATR в % от цены."""
    atr = calc_atr(df, period)
    close = float(df['close'].iloc[-1]) if not isinstance(df['close'].iloc[-1], bytes) else 0
    return (atr / close * 100) if close > 0 else 1.0

# ========== ОСНОВНОЙ ЦИКЛ ==========
def main():
    print("=" * 60)
    print("🤖 РОБОТ АКЦИЙ |", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    print("=" * 60)
    print(f"Акций: {len(STOCKS)}")
    print(f"Секторов: {len(SECTOR_MAP)}")
    print(f"Депозит: {DEPOSIT}₽")
    print(f"MAX_POSITIONS: {MAX_POSITIONS}")
    print("=" * 60)

    init_db()

    # Неторговый день — только стопы
    if not is_moex_trading_day():
        print('⏸️ Неторговый день — новые позиции не открываются')
        check_stops_only()
        return

    # Макро-фильтры
    macro = get_macro_filters()
    print(f"TRIN: {macro['trin']['trin']:.2f}")
    print(f"RVI: {macro['rvi']:.1f}")
    print(f"Режим: {macro['regime']['regime']} ({macro['regime']['score']}/100)")
    print(f"Сессия: {macro['session']['label']} (ликвидность {macro['session']['liquidity']:.0%})")
    print(f"Zweig: {macro['zweig']['signal']} ({macro['zweig']['label']})")

    # Порог входа
    if macro['zweig']['signal'] == 'BLOCKED':
        print('⛔ Zweig BLOCKED — не торгуем')
        entry_threshold = 999
    elif macro['zweig']['signal'] == 'CAUTION':
        entry_threshold = ENTRY_SCORE_CAUTION
        print(f'⚠️ Zweig CAUTION — порог {entry_threshold}')
    else:
        entry_threshold = ENTRY_SCORE_THRESHOLD
        print(f'✅ Zweig APPROVED — порог {entry_threshold}')

    if entry_threshold >= 999:
        return

    # Сканирование
    open_positions = get_open_positions()
    open_tickers = {p[1] for p in open_positions}

    print(f'\nОткрыто позиций: {len(open_positions)}/{MAX_POSITIONS}')
    print(f'Торговое время: {is_trading_time()}')
    print()

    if not is_trading_time():
        print('⏰ Вне торгового времени — не открываем')
        return

    for ticker in STOCKS:
        if len(open_positions) >= MAX_POSITIONS:
            print(f'⛔ Лимит позиций ({MAX_POSITIONS})')
            break
        if ticker in open_tickers:
            continue
        if is_in_cooldown(ticker):
            print(f'  ⏸️ {ticker}: cooldown')
            continue

        try:
            # Данные (с проверкой существования файлов)
            df_d1_file = DATA_ROOT / 'candles' / f'{ticker}_D1.parquet'
            df_h1_file = DATA_ROOT / 'candles' / f'{ticker}_H1.parquet'
            df_m10_file = DATA_ROOT / 'candles' / f'{ticker}_M10.parquet'
            if not df_d1_file.exists() or not df_h1_file.exists() or not df_m10_file.exists():
                continue
            df_d1 = pd.read_parquet(df_d1_file)
            df_h1 = pd.read_parquet(df_h1_file)
            df_m10 = pd.read_parquet(df_m10_file)

            if len(df_d1) < 30 or len(df_h1) < 30 or len(df_m10) < 30:
                continue

            # HI2
            hi2 = get_hi2_for_ticker(ticker)
            if hi2 is None:
                continue
            hi2_value = hi2.get('hhi_agressive')

            # GARCH
            garch = calculate_garch_for_ticker(df_d1, ticker)
            garch_vol = garch.get('garch_vol', 0) or 0

            # Сектор
            sector = get_sector_for(ticker, df_d1)

            # ADX/Chop
            adx = calculate_adx(df_d1).iloc[-1]
            chop = calculate_choppiness(df_d1).iloc[-1]
            atr_pct = calc_atr_pct(df_d1)

            # Вердикт
            verdict = get_stock_scanner_verdict(
                df_d1, df_h1, df_m10,
                hi2_value=hi2_value,
                garch_vol=garch_vol,
                sector_trend=sector['sector_trend'],
                chop_val=chop, adx_val=adx,
                atr_pct=atr_pct,
                relative_strength=sector['relative_strength'],
                volume_spike=False,
                trin_value=macro['trin']['trin']
            )

            decision = verdict.get('decision', 'WAIT')
            score = verdict.get('score', 0)

            # ===== ВОЛАТИЛЬНОСТНЫЙ ФИЛЬТР =====
            if atr_pct > 3.0:
                print(f'  ⏸️ {ticker}: ATR%={atr_pct:.2f} > 3.0% — слишком волатильно')
                continue
            if atr_pct < 0.5:
                print(f'  ⏸️ {ticker}: ATR%={atr_pct:.2f} < 0.5% — слишком спокойно')
                continue
            if garch_vol > 25.0:
                print(f'  ⏸️ {ticker}: GARCH={garch_vol:.2f} > 25.0 — аномальная волатильность')
                continue

            if decision == 'LONG' and score >= entry_threshold:
                price = float(df_m10['close'].iloc[-1]) if not isinstance(df_m10['close'].iloc[-1], bytes) else 0
                atr = calc_atr(df_d1)
                if price > 0 and atr > 0:
                    open_position(ticker, score, price, atr)
                    open_tickers.add(ticker)
                    open_positions.append((None, ticker))
            else:
                pass  # тихо

        except Exception as e:
            print(f'  ❌ {ticker}: {e}')

    print("\n✅ Проверка завершена")


if __name__ == '__main__':
    while True:
        try:
            main()
            print('Ожидание 1 час (стопы проверяются каждые 10 мин)...')

            for i in range(6):
                time.sleep(600)
                check_stops_only()
                print(f'  [{i+1}/6] Проверка стопов завершена')
        except KeyboardInterrupt:
            print('🛑 Остановлено пользователем')
            break
        except Exception as e:
            print(f'❌ Ошибка в main: {e}')
            time.sleep(60)
