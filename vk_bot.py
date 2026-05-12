import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
import pandas as pd
from pathlib import Path
from datetime import datetime
import json
import random

# ========== КОНФИГ ==========
TOKEN = "vk1.a.SlI9YR5W8dTnTYhVLlhNxXEmgDo6rImtWM1jEIpsZKb9KR8EB_x325YDm_Piu1QZffsffqKethgXWlBH3G0e_6h9DUmZEVzbCmXajTm3jW33hE1F49dUOVtjHGRLYN_5pYOnLN0ZiFpdu_DVVqPHLfShNWDBN1prFS7Yf1ec-PE75C_hhs5Mo7SANbnE_uWzA3dGP3_l3So8HfcUVW3f8A"
GROUP_ID = 238639379
DATA_ROOT = Path("/root/finlab/data")

# ========== ФУНКЦИИ ДАННЫХ ==========
def get_collectors_status():
    """Статус всех сборщиков"""
    status_lines = ["📊 Статус сборщиков:", ""]
    
    collectors = {
        "FutOI": DATA_ROOT / "futoi",
        "HI2": DATA_ROOT / "hi2",
        "Funding": DATA_ROOT / "funding" / "funding.parquet",
        "Super Candles": DATA_ROOT / "supercandles",
        "Super Candles H4": DATA_ROOT / "supercandles_h4"
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
    """Текущий сигнал FutOI по всем тикерам"""
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
                lines.append(f"{ticker}: нет данных по физикам")
                continue
            
            df_fiz['datetime'] = pd.to_datetime(
                df_fiz['tradedate'].astype(str) + ' ' + df_fiz['tradetime'].astype(str)
            )
            df_fiz = df_fiz.sort_values(['datetime', 'seqnum'])
            df_agg = df_fiz.groupby('datetime').last().reset_index()
            
            if len(df_agg) >= 2:
                latest = df_agg.iloc[-1]
                prev = df_agg.iloc[-2]
                delta = latest['pos'] - prev['pos']
                signal = "🟢" if latest['pos'] > 0 else "🔴"
                lines.append(
                    f"{signal} {ticker}: {latest['pos']:+,.0f} "
                    f"(Δ {delta:+,.0f}) | L:{latest['pos_long']:,.0f} S:{latest['pos_short']:,.0f}"
                    .replace(",", " ")
                )
        except Exception as e:
            lines.append(f"⚠️ {ticker}: ошибка чтения")
    
    return "\n".join(lines)

def get_funding_rates():
    """Текущие ставки фандинга"""
    funding_path = DATA_ROOT / "funding" / "funding.parquet"
    if not funding_path.exists():
        return "❌ Данные фандинга не найдены"
    
    try:
        df = pd.read_parquet(funding_path)
        if df.empty:
            return "❌ Нет данных фандинга"
        
        lines = ["💰 Ставки фандинга:", ""]
        
        # Берём последние записи для каждого тикера
        if 'ticker' in df.columns:
            latest = df.sort_values('timestamp' if 'timestamp' in df.columns else df.columns[0])
            latest = latest.drop_duplicates(subset=['ticker'], keep='last')
            
            for _, row in latest.iterrows():
                ticker = row.get('ticker', '?')
                rate = row.get('rate', row.get('funding_rate', 0))
                lines.append(f"{ticker}: {rate:+.4%}" if isinstance(rate, float) else f"{ticker}: {rate}")
        else:
            lines.append(f"Данные: {df.tail(5).to_string()}")
        
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Ошибка чтения фандинга: {e}"

# ========== ОСНОВНОЙ КОД ==========
def main():
    vk_session = vk_api.VkApi(token=TOKEN)
    longpoll = VkBotLongPoll(vk_session, GROUP_ID)
    vk = vk_session.get_api()
    
    print("🤖 VK Bot запущен. Ожидание команд...")
    
    for event in longpoll.listen():
        if event.type == VkBotEventType.MESSAGE_NEW:
            msg = event.object.message
            text = msg.get('text', '').lower().strip()
            peer_id = msg.get('peer_id')
            
            if text == '/status':
                response = get_collectors_status()
            elif text == '/futoi':
                response = get_futoi_signal()
            elif text == '/funding':
                response = get_funding_rates()
            elif text == '/help':
                response = "📋 Доступные команды:\n/status — статус сборщиков\n/futoi — сигналы FutOI\n/funding — ставки фандинга"
            else:
                response = "Неизвестная команда. Используйте /help для списка команд."
            
            try:
                vk.messages.send(
                    peer_id=peer_id,
                    message=response[:4096],  # Лимит ВК на длину сообщения
                    random_id=random.randint(1, 2**31 - 1)
                )
                print(f"✅ Ответ отправлен на /{text}")
            except Exception as e:
                print(f"❌ Ошибка отправки: {e}")

if __name__ == '__main__':
    main()
