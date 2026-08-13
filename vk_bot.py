import os
import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
import json
import random
import time
import threading

# ========== КОНФИГ ==========
TOKEN = "vk1.a.SlI9YR5W8dTnTYhVLlhNxXEmgDo6rImtWM1jEIpsZKb9KR8EB_x325YDm_Piu1QZffsffqKethgXWlBH3G0e_6h9DUmZEVzbCmXajTm3jW33hE1F49dUOVtjHGRLYN_5pYOnLN0ZiFpdu_DVVqPHLfShNWDBN1prFS7Yf1ec-PE75C_hhs5Mo7SANbnE_uWzA3dGP3_l3So8HfcUVW3f8A"
GROUP_ID = 238639379; ADMIN_ID = 497763452
DATA_ROOT = Path("/root/finlab/data")
STATE_FILE = Path("/root/finlab/logs/trend_state.json")

TICKERS = ["CNYRUBF", "GAZPF", "GLDRUBF", "IMOEXF", "SBERF"]
MAX_CHAT_MESSAGES = 5  # Автоочистка при >5 сообщений

# ========== ФУНКЦИИ ДАННЫХ ==========
def get_collectors_status():
    status_lines = ["📊 Статус сборщиков:", ""]
    collectors = {
        "FutOI": DATA_ROOT / "futoi",
        "HI2": DATA_ROOT / "hi2",
        "Funding": DATA_ROOT / "funding" / "funding.parquet",
        "Super Candles": DATA_ROOT / "supercandles",
        "Super Candles H4": DATA_ROOT / "supercandles_h4",
        "TradeStats": DATA_ROOT / "tradestats",
        "Candles": DATA_ROOT / "candles"
    }
    for name, path in collectors.items():
        if path.exists():
            if path.is_dir():
                files = list(path.glob("*.parquet"))
                if files:
                    total_rows = sum(len(pd.read_parquet(f)) for f in files if f.stat().st_size > 0)
                    last_mod = datetime.fromtimestamp(max(f.stat().st_mtime for f in files))
                    status_lines.append(f"✅ {name}: {total_rows:,} записей | {last_mod.strftime('%d.%m %H:%M')}".replace(",", " "))
                else:
                    status_lines.append(f"⚠️ {name}: нет файлов")
            else:
                if path.stat().st_size > 0:
                    df = pd.read_parquet(path)
                    last_mod = datetime.fromtimestamp(path.stat().st_mtime)
                    status_lines.append(f"✅ {name}: {len(df):,} записей | {last_mod.strftime('%d.%m %H:%M')}".replace(",", " "))
                else:
                    status_lines.append(f"⚠️ {name}: файл пуст")
        else:
            status_lines.append(f"❌ {name}: путь не найден")
    return "\n".join(status_lines)

def get_futoi_signal():
    futoi_path = DATA_ROOT / "futoi"
    if not futoi_path.exists():
        return "❌ Данные FutOI не найдены"
    files = list(futoi_path.glob("*_futoi.parquet"))
    if not files:
        return "❌ Нет файлов FutOI"
    lines = ["📈 FutOI — чистая позиция физиков:", ""]
    for f in sorted(files):
        ticker = f.stem.replace("_futoi", "")
        try:
            df = pd.read_parquet(f)
            df_fiz = df[df['clgroup'] == 'FIZ'].copy()
            if df_fiz.empty:
                lines.append(f"{ticker}: нет данных")
                continue
            df_fiz['datetime'] = pd.to_datetime(df_fiz['tradedate'].astype(str) + ' ' + df_fiz['tradetime'].astype(str))
            df_fiz = df_fiz.sort_values(['datetime', 'seqnum'])
            df_agg = df_fiz.groupby('datetime').last().reset_index()
            if len(df_agg) >= 2:
                latest = df_agg.iloc[-1]
                prev = df_agg.iloc[-2]
                delta = latest['pos'] - prev['pos']
                signal = "🟢" if latest['pos'] > 0 else "🔴"
                lines.append(f"{signal} {ticker}: {latest['pos']:+,.0f} (Δ {delta:+,.0f})".replace(",", " "))
        except Exception as e:
            lines.append(f"⚠️ {ticker}: ошибка чтения")
    return "\n".join(lines)

def get_funding_rates():
    funding_path = DATA_ROOT / "funding" / "funding.parquet"
    if not funding_path.exists():
        return "❌ Данные фандинга не найдены"
    try:
        df = pd.read_parquet(funding_path)
        if df.empty:
            return "❌ Нет данных фандинга"
        lines = ["💰 Ставки фандинга:", ""]
        if 'ticker' in df.columns:
            latest = df.sort_values('timestamp' if 'timestamp' in df.columns else df.columns[0])
            latest = latest.drop_duplicates(subset=['ticker'], keep='last')
            for _, row in latest.iterrows():
                ticker = row.get('ticker', '?')
                rate = row.get('swaprate', 0)
                lines.append(f"{ticker}: {rate:+.4%}" if isinstance(rate, float) else f"{ticker}: {rate}")
        else:
            lines.append(f"Данные: {df.tail(5).to_string()}")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Ошибка чтения фандинга: {e}"

def get_close_price(ticker):
    """Получить последнюю цену закрытия"""
    try:
        f = DATA_ROOT / "candles" / f"{ticker}_D1.parquet"
        if not f.exists():
            return None
        df = pd.read_parquet(f)
        if len(df) == 0:
            return None
        return df["close"].iloc[-1]
    except:
        return None

def get_trend_for_ticker(ticker):
    """Определяет текущий тренд тикера: LONG/SHORT/NEUTRAL"""
    try:
        f = DATA_ROOT / "futoi" / f"{ticker}_futoi.parquet"
        if not f.exists():
            return None
        df = pd.read_parquet(f)
        df_fiz = df[df['clgroup'] == 'FIZ'].copy()
        if df_fiz.empty:
            return None
        df_fiz['datetime'] = pd.to_datetime(df_fiz['tradedate'].astype(str) + ' ' + df_fiz['tradetime'].astype(str))
        df_fiz = df_fiz.sort_values(['datetime', 'seqnum'])
        df_agg = df_fiz.groupby('datetime').last().reset_index()
        if len(df_agg) < 2:
            return None
        latest = df_agg.iloc[-1]
        prev = df_agg.iloc[-2]
        delta = latest['pos'] - prev['pos']
        # Определяем тренд
        if latest['pos'] > 0 and delta > 0:
            return "LONG"
        elif latest['pos'] < 0 and delta < 0:
            return "SHORT"
        else:
            return "NEUTRAL"
    except:
        return None

def load_state():
    """Загружает предыдущее состояние трендов"""
    if STATE_FILE.exists():
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_state(state):
    """Сохраняет состояние трендов"""
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)

def auto_cleanup(vk, peer_id):
    """Удаляет старые сообщения, оставляя последние MAX_CHAT_MESSAGES"""
    try:
        history = vk.messages.getHistory(peer_id=peer_id, count=20)
        messages = history.get('items', [])
        # Оставляем последние MAX_CHAT_MESSAGES, удаляем остальные
        if len(messages) > MAX_CHAT_MESSAGES:
            for msg in messages[MAX_CHAT_MESSAGES:]:
                try:
                    vk.messages.delete(message_id=msg['id'], delete_for_all=1)
                except:
                    pass
    except:
        pass


def check_data_freshness():
    from datetime import datetime
    now = datetime.now()
    problems = []
    
    # Проверка MOEX_TOKEN
    token = os.getenv('MOEX_TOKEN')
    if not token:
        try:
            from dotenv import load_dotenv
            load_dotenv('/root/finlab/.env')
            token = os.getenv('MOEX_TOKEN')
        except:
            pass
    if not token:
        problems.append("❌ MOEX_TOKEN не установлен — сборщики не работают")
    
    checks = {
        "FutOI": (DATA_ROOT / "futoi", 1),
        "HI2": (DATA_ROOT / "hi2", 2),
        "Super Candles": (DATA_ROOT / "supercandles", 1),
        "TradeStats": (DATA_ROOT / "tradestats", 1),
        "H4 фьючерсов": (DATA_ROOT / "candles", 1),
    }
    for name, (dir_path, max_days) in checks.items():
        if not dir_path.exists():
            problems.append(f"❌ {name}: папка не найдена")
            continue
        files = list(dir_path.glob("*.parquet"))
        if not files:
            problems.append(f"⚠️ {name}: нет файлов")
            continue
        last_mod = datetime.fromtimestamp(max(f.stat().st_mtime for f in files))
        days_old = (now - last_mod).days
        if days_old > max_days:
            problems.append(f"🔴 {name}: {days_old} дн. назад ({last_mod.strftime("%d.%m.%Y %H:%M")})")
    return problems

def check_trend_changes(vk):
    """Проверяет смену трендов и отправляет уведомления"""
    prev_state = load_state()
    changes = []
    
    for ticker in TICKERS:
        current_trend = get_trend_for_ticker(ticker)
        if current_trend is None:
            continue
        
        prev_trend = prev_state.get(ticker)
        prev_state[ticker] = current_trend
        
        if prev_trend and prev_trend != current_trend:
            emoji = "🟢" if current_trend == "LONG" else ("🔴" if current_trend == "SHORT" else "⚪")
            price = get_close_price(ticker)
            price_str = f" ({price:.1f}₽)" if price is not None else ""
            changes.append(f"{emoji} {ticker}{price_str}: {prev_trend} → {current_trend}")
    
    save_state(prev_state)
    
    if changes:
        msg = "🔄 Смена тренда:\n" + "\n".join(changes)
        try:
            vk.method('messages.send', {
                'peer_id': ADMIN_ID,
                'message': msg,
                'random_id': random.randint(1, 2**31 - 1)
            })
            print(f"📤 Уведомление о смене тренда: {len(changes)} тикеров")
            auto_cleanup(vk, GROUP_ID)
        except Exception as e:
            print(f"❌ Ошибка отправки уведомления: {e}")


def auto_stale_check(vk):
    """Автоматическая проверка свежести каждые 6 часов."""
    import time as _time
    while True:
        problems = check_data_freshness()
        if problems:
            msg = "⚠️ Авто-проверка свежести:\n" + "\n".join(problems)
            try:
                vk.method('messages.send', {
                    'peer_id': ADMIN_ID,
                    'message': msg,
                    'random_id': random.randint(1, 2**31 - 1)
                })
                print(f"Отправлено уведомление о свежести: {len(problems)} проблем(ы)")
            except Exception as e:
                print(f"Ошибка отправки: {e}")
        _time.sleep(21600)

def trend_monitor(vk):
    """Фоновый мониторинг трендов (каждые 10 минут)"""
    while True:
        try:
            check_trend_changes(vk)
        except Exception as e:
            print(f"❌ Ошибка мониторинга трендов: {e}")
        time.sleep(600)  # Каждые 10 минут

# ========== ОСНОВНОЙ КОД ==========
def main():
    connection_lost = False
    monitor_started = False

    while True:
        try:
            vk_session = vk_api.VkApi(token=TOKEN)
            longpoll = VkBotLongPoll(vk_session, GROUP_ID)
            vk = vk_session.get_api()

            print("🤖 VK Bot запущен. Ожидание команд...")

            # Запускаем фоновый мониторинг трендов (один раз)
            if not monitor_started:
                monitor_thread = threading.Thread(target=trend_monitor, args=(vk,), daemon=True)
                monitor_thread.start()
                monitor_started = True

                # Авто-проверка свежести (каждые 6 часов)
                stale_thread = threading.Thread(target=auto_stale_check, args=(vk,), daemon=True)
                stale_thread.start()
                print("📡 Мониторинг трендов запущен (каждые 10 мин)")

            if connection_lost:
                try:
                    vk.method('messages.send', {
                        'peer_id': ADMIN_ID,
                        'message': "✅ Связь с сервером VK восстановлена. Бот работает.",
                        'random_id': random.randint(1, 2**31 - 1)
                    })
                except:
                    pass
                connection_lost = False

            for event in longpoll.listen():
                if event.type == VkBotEventType.MESSAGE_NEW:
                    msg = event.object.message
                    text = msg.get('text', '').lower().strip()
                    peer_id = msg.get('peer_id')

                    if str(peer_id) == str(GROUP_ID):
                        continue

                    if text in ['status', '/status']:
                        response = get_collectors_status()
                    elif text in ['futoi', '/futoi']:
                        response = get_futoi_signal()
                    elif text in ['funding', '/funding']:
                        response = get_funding_rates()
                    elif text in ['help', '/help']:
                        response = "📋 Доступные команды:\nstatus — статус сборщиков\nfutoi — сигналы FutOI\nfunding — ставки фандинга\nstale — проверка свежести"
                    elif msg == "stale":
                        problems = check_data_freshness()
                        if problems:
                            response = "🔴 Проблемы со свежестью данных:\n" + "\n".join(problems)
                        else:
                            response = "✅ Все данные свежие"
                    else:
                        response = "Неизвестная команда. Используйте help для списка команд."

                    try:
                        vk.method('messages.send', {
                            'peer_id': peer_id,
                            'message': response[:4096],
                            'random_id': random.randint(1, 2**31 - 1)
                        })
                        print(f"✅ Ответ отправлен на /{text}")
                    except Exception as e:
                        print(f"❌ Ошибка отправки: {e}")

        except Exception as e:
            print(f"❌ Ошибка соединения: {e}")
            connection_lost = True
            time.sleep(30)

if __name__ == '__main__':
    main()
