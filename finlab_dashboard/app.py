
import streamlit as st
from pathlib import Path
import pandas as pd
import os
from datetime import datetime
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ========== КОНФИГ ==========
DATA_ROOT = Path("/root/finlab/data")
LOGS_ROOT = Path("/root/finlab/logs")

# ========== ФУНКЦИИ ДЛЯ СТАТУСОВ ==========
def parse_log_date(filename: str) -> datetime:
    try:
        date_str = filename.split('_')[0]
        return datetime.strptime(date_str, '%Y-%m-%d')
    except:
        return None

def get_folder_stats(folder_path: Path) -> dict:
    if not folder_path.exists():
        return {"status": "❌", "files": 0, "total_rows": 0, "last_modified": None}
    parquet_files = list(folder_path.glob("*.parquet"))
    if not parquet_files:
        return {"status": "⚠️", "files": 0, "total_rows": 0, "last_modified": None}
    total_rows = 0
    last_modified = None
    for f in parquet_files:
        try:
            df = pd.read_parquet(f)
            total_rows += len(df)
            mtime = os.path.getmtime(f)
            if last_modified is None or mtime > last_modified:
                last_modified = mtime
        except Exception as e:
            st.warning(f"Ошибка чтения {f.name}: {e}")
    return {"status": "✅", "files": len(parquet_files), "total_rows": total_rows, "last_modified": last_modified}

def get_last_log_info(collector_name: str) -> tuple:
    if not LOGS_ROOT.exists():
        return None, "нет логов"
    logs = sorted(LOGS_ROOT.glob(f"*{collector_name}*.log"), reverse=True)
    if logs:
        last_log = logs[0]
        date = parse_log_date(last_log.name)
        return date, last_log.name
    return None, "нет логов"

# ========== ЗАГРУЗКА ДАННЫХ ==========
@st.cache_data
def load_futoi_data():
    futoi_path = DATA_ROOT / "futoi"
    if not futoi_path.exists():
        return None, []
    files = list(futoi_path.glob("*_futoi.parquet"))
    if not files:
        return None, []
    dfs = []
    for f in files:
        try:
            df = pd.read_parquet(f)
            dfs.append(df)
        except:
            pass
    if not dfs:
        return None, []
    all_data = pd.concat(dfs, ignore_index=True)
    tickers = sorted(all_data['ticker'].unique())
    return all_data, tickers

@st.cache_data
def load_supercandles_data():
    sc_path = DATA_ROOT / "supercandles"
    if not sc_path.exists():
        return None, []
    files = list(sc_path.glob("*_supercandles.parquet"))
    if not files:
        return None, []
    dfs = []
    for f in files:
        try:
            df = pd.read_parquet(f)
            dfs.append(df)
        except:
            pass
    if not dfs:
        return None, []
    all_data = pd.concat(dfs, ignore_index=True)
    tickers = sorted(all_data['secid'].unique())

@st.cache_data
def load_hi2_data():
    """Загружает все данные HI2, возвращает DataFrame с колонками ticker, tradedate, metric, value"""
    hi2_path = DATA_ROOT / "hi2"
    if not hi2_path.exists():
        return None
    files = list(hi2_path.glob("*_hi2.parquet"))
    if not files:
        return None
    dfs = []
    for f in files:
        try:
            df = pd.read_parquet(f)
            dfs.append(df)
        except:
            pass
    if not dfs:
        return None
    all_data = pd.concat(dfs, ignore_index=True)
    all_data['tradedate'] = pd.to_datetime(all_data['tradedate'])
    return all_data

# ========== ФУНКЦИИ АНАЛИТИКИ FUTOI ==========
def calculate_delta_1h(df_analytics):
    """Расчёт дельты за 1 час для fiz_buy_ratio и yur_buy_ratio"""
    if df_analytics is None or len(df_analytics) < 2:
        return None, None
    
    latest = df_analytics.iloc[-1]
    latest_time = latest['datetime']
    target_time = latest_time - pd.Timedelta(hours=1)
    
    # Ищем ближайшую строку к 1 часу назад
    df_before = df_analytics[df_analytics['datetime'] <= target_time]
    if len(df_before) == 0:
        return None, None
    
    prev = df_before.iloc[-1]
    
    delta_fiz = latest['fiz_buy_ratio'] - prev['fiz_buy_ratio']
    delta_yur = latest['yur_buy_ratio'] - prev['yur_buy_ratio']
    
    return delta_fiz, delta_yur

def prepare_futoi_analytics(df_ticker):
    df_ticker['datetime'] = pd.to_datetime(df_ticker['tradedate'].astype(str) + ' ' + df_ticker['tradetime'].astype(str))
    df_fiz = df_ticker[df_ticker['clgroup'] == 'FIZ'].copy()
    df_yur = df_ticker[df_ticker['clgroup'] == 'YUR'].copy()
    df_fiz = df_fiz.sort_values(['datetime', 'seqnum'])
    df_yur = df_yur.sort_values(['datetime', 'seqnum'])
    df_fiz_agg = df_fiz.groupby('datetime').last().reset_index()
    df_yur_agg = df_yur.groupby('datetime').last().reset_index()
    df_merged = pd.merge(
        df_fiz_agg[['datetime', 'pos', 'pos_long', 'pos_short', 'pos_long_num', 'pos_short_num']],
        df_yur_agg[['datetime', 'pos', 'pos_long', 'pos_short', 'pos_long_num', 'pos_short_num']],
        on='datetime', suffixes=('_fiz', '_yur'), how='outer'
    ).sort_values('datetime')
    df_merged = df_merged.ffill().fillna(0)
    df_merged['phys_net'] = df_merged['pos_fiz']
    df_merged['corp_net'] = df_merged['pos_yur']
    df_merged['fiz_buy_ratio'] = df_merged['pos_long_num_fiz'] / (df_merged['pos_long_num_fiz'] + df_merged['pos_short_num_fiz'] + 1) * 100
    df_merged['yur_buy_ratio'] = df_merged['pos_long_num_yur'] / (df_merged['pos_long_num_yur'] + df_merged['pos_short_num_yur'] + 1) * 100
    df_merged['fiz_yur_ratio'] = df_merged['phys_net'] / (abs(df_merged['corp_net']) + 1)
    df_merged['fiz_volume'] = df_merged['pos_long_fiz'] + df_merged['pos_short_fiz']
    df_merged['yur_volume'] = df_merged['pos_long_yur'] + df_merged['pos_short_yur']
    return df_merged
def calculate_atr(df_d1, period=14):
    """Расчёт Average True Range (волатильности)"""
    if df_d1 is None or len(df_d1) < period + 1:
        return None, "Недостаточно данных"
    
    df = df_d1.copy()
    df['high'] = pd.to_numeric(df['high'], errors='coerce')
    df['low'] = pd.to_numeric(df['low'], errors='coerce')
    df['close'] = pd.to_numeric(df['close'], errors='coerce')
    
    # True Range
    df['tr'] = df[['high', 'low', 'close']].apply(
        lambda row: max(
            row['high'] - row['low'],
            abs(row['high'] - row['close']),
            abs(row['low'] - row['close'])
        ) if pd.notna(row[['high', 'low', 'close']]).all() else 0,
        axis=1
    )
    
    # ATR
    df['atr'] = df['tr'].rolling(period).mean()
    
    current_atr = df['atr'].iloc[-1]
    avg_close = df['close'].tail(period).mean()
    atr_pct = (current_atr / avg_close * 100) if avg_close > 0 else 0
    
    # Определяем уровень волатильности
    if atr_pct < 1.0:
        level = "Низкая"
        emoji = "🔵"
    elif atr_pct < 2.5:
        level = "Нормальная"
        emoji = "🟢"
    elif atr_pct < 5.0:
        level = "Высокая"
        emoji = "🟡"
    else:
        level = "Экстремальная"
        emoji = "🔴"
    
    return {
        'atr': current_atr,
        'atr_pct': atr_pct,
        'level': level,
        'emoji': emoji
    }, None

def calculate_signals(df, df_d1=None, df_ts=None, atr_info=None, hi2_info=None):
    """Расчёт торговых сигналов с единым вердиктом (v3.4)"""
    if len(df) < 3:
        return "NEUTRAL", "Недостаточно данных", "⚪", [], None, None, None
    history = []
    for i in range(max(0, len(df) - 10), len(df)):
        if i < 3:
            continue
        window = df.iloc[:i+1]
        latest = window.iloc[-1]
        prev = window.iloc[-2]
        strength = 0
        if latest['phys_net'] > prev['phys_net']:
            strength += 1
        elif latest['phys_net'] < prev['phys_net']:
            strength -= 1
        if latest['fiz_buy_ratio'] > 60:
            strength += 1
        elif latest['fiz_buy_ratio'] < 40:
            strength -= 1
        if latest['fiz_yur_ratio'] > 0.5 and latest['phys_net'] > 0:
            strength += 1
        elif latest['fiz_yur_ratio'] < -0.5 and latest['phys_net'] < 0:
            strength -= 1
        if strength >= 2:
            signal_type = "LONG"
        elif strength <= -2:
            signal_type = "SHORT"
        else:
            signal_type = "NEUTRAL"
        divergence = False
        if i >= 5:
            pos_change = latest['phys_net'] - df.iloc[i-3]['phys_net']
            vol_change = latest['fiz_volume'] - df.iloc[i-3]['fiz_volume']
            if (pos_change > 0 and vol_change < 0) or (pos_change < 0 and vol_change > 0):
                divergence = True
        history.append({
            'datetime': latest['datetime'],
            'signal': signal_type, 'strength': strength, 'divergence': divergence,
            'fiz_buy_ratio': latest['fiz_buy_ratio'], 'yur_buy_ratio': latest['yur_buy_ratio'],
            'phys_net': latest['phys_net'], 'corp_net': latest['corp_net'],
            'fiz_yur_ratio': latest['fiz_yur_ratio'], 'fiz_volume': latest['fiz_volume'], 'yur_volume': latest['yur_volume']
        })
    if not history:
        return "NEUTRAL", "Недостаточно данных", "⚪", [], None, None, None
    current = history[-1]
    signal_type = current['signal']
    fiz_overheated = current['fiz_buy_ratio'] > 80
    fiz_oversold = current['fiz_buy_ratio'] < 20
    yur_buying = current['yur_buy_ratio'] > 50
    yur_selling = current['yur_buy_ratio'] < 50

    trend_is_down = False
    trend_is_up = False
    price_below_poc = False
    is_distribution = current['phys_net'] > 0 and current['corp_net'] < 0
    is_accumulation = current['phys_net'] < 0 and current['corp_net'] > 0
    is_unity_long = current['phys_net'] > 0 and current['corp_net'] > 0
    is_unity_short = current['phys_net'] < 0 and current['corp_net'] < 0

    poc_price = None
    high_20 = None
    low_20 = None

    if df_d1 is not None and len(df_d1) >= 20:
        if 'sma20' not in df_d1.columns:
            df_d1['sma20'] = df_d1['close'].rolling(20).mean()
        last_close = df_d1['close'].iloc[-1]
        sma20 = df_d1['sma20'].iloc[-1]
        high_20 = df_d1['high'].tail(20).max()
        low_20 = df_d1['low'].tail(20).min()
        if last_close < sma20 * 0.98:
            trend_is_down = True
        elif last_close > sma20 * 1.02:
            trend_is_up = True

    if df_ts is not None and len(df_ts) > 0:
        df_ts['price_level'] = df_ts['pr_close'].round(1)
        vol_profile = df_ts.groupby('price_level')['vol'].sum().reset_index()
        if len(vol_profile) > 0:
            poc_price = vol_profile.loc[vol_profile['vol'].idxmax(), 'price_level']
            if df_d1 is not None and len(df_d1) > 0:
                if last_close < poc_price:
                    price_below_poc = True

    # === ПРАВИЛА БЛОКИРОВКИ ===
    block_reasons = []
    if signal_type == "LONG":
        if fiz_overheated and yur_selling:
            signal_type = "WAIT_FOR_RETRACEMENT"
            block_reasons.append("Перекупленность + Юрики продают")
        else:
            if fiz_overheated:
                block_reasons.append("Перекупленность")
            if is_distribution:
                block_reasons.append("Дистрибуция")
            if trend_is_down:
                block_reasons.append("Нисходящий тренд")
            if price_below_poc:
                block_reasons.append("Цена ниже POC")
            if block_reasons:
                signal_type = "BLOCKED_LONG"

    if signal_type == "SHORT":
        if fiz_oversold and yur_buying:
            signal_type = "WAIT_FOR_BOUNCE"
            block_reasons.append("Перепроданность + Юрики покупают")
        else:
            if fiz_oversold:
                block_reasons.append("Перепроданность")
            if is_accumulation:
                block_reasons.append("Аккумуляция")
            if trend_is_up:
                block_reasons.append("Восходящий тренд")
            if block_reasons:
                signal_type = "BLOCKED_SHORT"

    # === ЕДИНЫЙ ВЕРДИКТ ===
    lines = []
    if signal_type == "LONG":
        lines.append(f"**🟢 Сигнал: ОТКРЫТИЕ ЛОНГА (подтверждён)**")
    elif signal_type == "SHORT":
        lines.append(f"**🔴 Сигнал: ОТКРЫТИЕ ШОРТА (подтверждён)**")
    elif signal_type == "WAIT_FOR_RETRACEMENT":
        lines.append(f"**🔴 КРИТИЧЕСКАЯ ПЕРЕГРЕТОСТЬ. ВХОД ТОЛЬКО НА ОТКАТЕ**")
    elif signal_type == "WAIT_FOR_BOUNCE":
        lines.append(f"**🟢 КРИТИЧЕСКАЯ ПЕРЕПРОДАННОСТЬ. ВХОД ТОЛЬКО НА ОТСКОКЕ**")
    elif signal_type == "BLOCKED_LONG":
        reasons = ", ".join(block_reasons)
        lines.append(f"**🔴 НЕ ВХОДИТЬ. Причины: {reasons}.**")
    elif signal_type == "BLOCKED_SHORT":
        reasons = ", ".join(block_reasons)
        lines.append(f"**🟢 НЕ ВХОДИТЬ. Причины: {reasons}.**")
    else:
        lines.append(f"**⚪ Сигнал: НЕЙТРАЛЬНО. Ждать формирования сигнала.**")

    lines.append("")
    lines.append("**📊 Торговый вердикт:**")
    lines.append("")
    lines.append("| Показатель | Значение |")
    lines.append("| :--- | :--- |")
    if df_d1 is not None and len(df_d1) >= 20:
        if 'sma20' not in df_d1.columns:
            df_d1['sma20'] = df_d1['close'].rolling(20).mean()
        last_close = df_d1['close'].iloc[-1]
        sma20 = df_d1['sma20'].iloc[-1]
        if last_close > sma20 * 1.02:
            trend = "Восходящий ▲"
        elif last_close < sma20 * 0.98:
            trend = "Нисходящий ▼"
        else:
            trend = "Боковик ◼"
        dist_to_support = (last_close - low_20) / last_close * 100
        dist_to_resist = (high_20 - last_close) / last_close * 100
        lines.append(f"| Таймфрейм анализа | D1 |")
        lines.append(f"| Тренд | {trend} |")
        lines.append(f"| Цена | {last_close:.2f} |")
        lines.append(f"| SMA 20 | {sma20:.2f} |")
        lines.append(f"| Сопротивление | {high_20:.2f} (дист. {dist_to_resist:.1f}%) |")
        lines.append(f"| Поддержка | {low_20:.2f} (дист. {dist_to_support:.1f}%) |")
    else:
        lines.append(f"| Тренд | Данные D1 недоступны |")
        lines.append(f"| Уровни | Данные D1 недоступны |")

    if poc_price is not None:
        lines.append(f"| POC (макс. объём) | {poc_price:.2f} |")
        if df_d1 is not None and len(df_d1) > 0:
            if last_close > poc_price:
                lines.append(f"| Цена vs POC | Выше → поддержка |")
            else:
                lines.append(f"| Цена vs POC | Ниже → сопротивление |")
        if atr_info is not None:
            lines.append(f"| Волатильность (ATR) | {atr_info['atr']:.2f} ({atr_info['atr_pct']:.1f}%) — {atr_info['emoji']} {atr_info['level']} |")
        if hi2_info is not None:
            delta_str = ""
            if hi2_info['delta'] is not None:
                arrow = "▲" if hi2_info['delta'] > 0 else "▼"
                delta_str = f" ({arrow} {abs(hi2_info['delta']):.0f} за сутки)"
            pct_str = f" ({hi2_info['pct']:.0f}% от макс. {hi2_info['max']:.0f})" if 'pct' in hi2_info else ""
            lines.append(f"| HI2 (концентрация) | {hi2_info['value']:.0f} — {hi2_info['emoji']} {hi2_info['level']}{delta_str}{pct_str} |")

    lines.append("")
    lines.append("| Группа | % | Доминирование | Действие |")
    lines.append("| :--- | :--- | :--- | :--- |")
    fiz_pct = current['fiz_buy_ratio']
    yur_pct = current['yur_buy_ratio']

    # Физики
    fiz_dom = "Доминируют" if fiz_pct > 65 or fiz_pct < 35 else "—"
    fiz_side = "покупателей" if fiz_pct > 50 else "продавцов"
    fiz_display = fiz_pct if fiz_pct > 50 else 100 - fiz_pct
    action_fiz = "Покупают" if current['phys_net'] > 0 else "Продают"

    # Юрики
    yur_dom = "Доминируют" if yur_pct > 65 or yur_pct < 35 else "—"
    yur_side = "покупателей" if yur_pct > 50 else "продавцов"
    yur_display = yur_pct if yur_pct > 50 else 100 - yur_pct
    action_yur = "Покупают" if current['corp_net'] > 0 else "Продают"

    # Общее действие
    if is_distribution:
        action_common = "Дистрибуция"
    elif is_accumulation:
        action_common = "Аккумуляция"
    elif is_unity_long:
        action_common = "Единство (лонг)"
    elif is_unity_short:
        action_common = "Единство (шорт)"
    else:
        action_common = "—"

    lines.append(f"| Физики | {fiz_display:.1f}% {fiz_side} | {fiz_dom} | {action_fiz} |")
    lines.append(f"| Юрики | {yur_display:.1f}% {yur_side} | {yur_dom} | {action_yur} |")
    lines.append(f"| Общее | — | — | {action_common} |")

    # === ПОЯСНЕНИЕ К СИТУАЦИИ ===
    lines.append("")
    lines.append("**📝 Анализ:**")
    if is_distribution and yur_pct > 50:
        lines.append(f"Большинство юриков ({yur_pct:.1f}%) покупает, но меньшинство ({100-yur_pct:.1f}%) продаёт так крупно, что чистая позиция юриков отрицательная. Крупные игроки продают толпе — **медвежий сигнал** (дистрибуция).")
    elif is_distribution:
        lines.append(f"Юрики продают ({yur_display:.1f}% продавцов). Крупные игроки продают толпе — **медвежий сигнал** (дистрибуция).")
    elif is_accumulation and yur_pct < 50:
        lines.append(f"Большинство юриков ({yur_display:.1f}%) продаёт, но меньшинство покупает так крупно, что чистая позиция юриков положительная. Крупные игроки набирают позицию у толпы — **бычий сигнал** (аккумуляция).")
    elif is_accumulation:
        lines.append(f"Юрики покупают ({yur_display:.1f}% покупателей). Крупные игроки набирают позицию у толпы — **бычий сигнал** (аккумуляция).")
    elif is_unity_long:
        lines.append(f"Обе группы покупают. Единство в лонге — **бычий сигнал**. Тренд поддерживается всеми участниками.")
    elif is_unity_short:
        lines.append(f"Обе группы продают. Единство в шорте — **медвежий сигнал**. Падение поддерживается всеми участниками.")
    elif yur_pct > 50 and current['corp_net'] > 0:
        lines.append(f"Большинство юриков ({yur_pct:.1f}%) покупает, но перевес небольшой. Юрики не доминируют — **нейтральный сигнал**.")
    elif yur_pct < 50 and current['corp_net'] < 0:
        lines.append(f"Большинство юриков ({yur_display:.1f}%) продаёт, но перевес небольшой. Юрики не доминируют — **нейтральный сигнал**.")
    
    # Добавляем анализ HI2
    if hi2_info is not None and hi2_info['level'] in ["Высокая", "Экстремальная"]:
        lines.append(f"")
        if hi2_info['level'] == "Экстремальная":
            lines.append(f"**🔍 HI2 = {hi2_info['value']:.0f} ({hi2_info['pct']:.0f}% от макс. — экстремальная концентрация):** Практически весь объём позиций сконцентрирован в руках 1-2 крупных игроков. Рынок полностью зависит от их действий.")
        else:
            lines.append(f"**🔍 HI2 = {hi2_info['value']:.0f} ({hi2_info['pct']:.0f}% от макс. — высокая концентрация):** Крупные игроки контролируют значительную часть позиций. Возможны резкие движения.")

    lines.append("")
    risk = []
    if fiz_overheated:
        risk.append("Перекупленность у физиков")
    elif fiz_oversold:
        risk.append("Перепроданность у физиков")
    if current['yur_buy_ratio'] > 80:
        risk.append("Перекупленность у юриков")
    elif current['yur_buy_ratio'] < 20:
        risk.append("Перепроданность у юриков")
    if is_distribution:
        risk.append("Дистрибуция (юрики продают)")
    elif is_accumulation:
        risk.append("Аккумуляция (юрики покупают)")
    if current['divergence']:
        risk.append("Дивергенция")
    if hi2_info is not None and hi2_info['level'] in ["Высокая", "Экстремальная"]:
        risk.append(f"Концентрация {hi2_info['level'].lower()} (HI2={hi2_info['value']:.0f}, {hi2_info['pct']:.0f}% от макс.)")
    lines.append(f"**Риск:** {', '.join(risk) if risk else 'Низкий'}.")
    lines.append("")
    lines.append(f"**Прогноз:**")
    if atr_info is not None and atr_info['level'] in ["Высокая", "Экстремальная"]:
        lines.append(f"⚠️ Волатильность {atr_info['level'].lower()}. Возможны резкие движения и выбитие стопов.")
    if signal_type == "LONG":
        lines.append(f"Высокая вероятность продолжения роста. Ближайшая цель — уровень сопротивления.")
    elif signal_type == "SHORT":
        lines.append(f"Высокая вероятность продолжения падения. Ближайшая цель — уровень поддержки.")
    elif signal_type == "BLOCKED_LONG":
        lines.append(f"Высокая вероятность продолжения падения или консолидации. Дождитесь разворота тренда или возврата цены выше POC.")
    elif signal_type == "BLOCKED_SHORT":
        lines.append(f"Высокая вероятность продолжения роста или консолидации. Дождитесь разворота тренда или возврата цены ниже POC.")
    elif signal_type == "WAIT_FOR_RETRACEMENT":
        lines.append(f"Ожидание коррекции вниз. После отката — вход в лонг от уровня поддержки.")
    elif signal_type == "WAIT_FOR_BOUNCE":
        lines.append(f"Ожидание отскока вверх. После отскока — вход в шорт от уровня сопротивления.")
    else:
        lines.append(f"Тренд не определён. Ждать формирования сигнала.")
    lines.append("")
    lines.append(f"**💡 Рекомендация:**")
    if atr_info is not None and atr_info['level'] in ["Высокая", "Экстремальная"]:
        lines.append(f"⚠️ Волатильность повышена. Увеличьте стоп в 1.5-2 раза. Рассмотрите выход из позиции.")
    if signal_type == "LONG":
        lines.append(f"Входить в лонг от уровня поддержки. Стоп под минимум дня. Цель — сопротивление.")
    elif signal_type == "SHORT":
        lines.append(f"Входить в шорт от уровня сопротивления. Стоп над максимум дня. Цель — поддержка.")
    elif signal_type == "WAIT_FOR_RETRACEMENT":
        lines.append(f"Ждать отката к уровню поддержки. Входить в лонг только после подтверждения разворота.")
    elif signal_type == "WAIT_FOR_BOUNCE":
        lines.append(f"Ждать отскока к уровню сопротивления. Входить в шорт только после подтверждения разворота.")
    elif signal_type == "BLOCKED_LONG":
        lines.append(f"Не входить в лонг. Ждать: 1) возврата цены выше POC, 2) разворота тренда на восходящий, 3) снижения перекупленности ниже 80%.")
    elif signal_type == "BLOCKED_SHORT":
        lines.append(f"Не входить в шорт. Ждать: 1) возврата цены ниже POC, 2) разворота тренда на нисходящий, 3) снижения перепроданности выше 20%.")
    else:
        lines.append(f"Ждать. Сигнал не сформирован.")

    if len(history) >= 3:
        last_signals = [h['signal'] for h in history[-3:]]
        prev_signal = last_signals[-2]
        if last_signals[-1] != prev_signal:
            lines.append("")
            prev_emoji = "🟢" if prev_signal == "LONG" else "🔴" if prev_signal == "SHORT" else "⚪"
            lines.append(f"🔄 **Смена сигнала:** предыдущий был {prev_emoji} {prev_signal}")

    signal_info = "\n".join(lines)
    signal_emoji = "🟢" if signal_type == "LONG" else "🔴" if signal_type in ["SHORT", "WAIT_FOR_RETRACEMENT", "BLOCKED_LONG"] else "⚪"
    return signal_type, signal_info, signal_emoji, history, poc_price, high_20, low_20
# ========== СБОР ДАННЫХ ДЛЯ ДАШБОРДА ==========
collectors_info = {}
futoi_stats = get_folder_stats(DATA_ROOT / "futoi")
futoi_date, futoi_log = get_last_log_info("futoi_collector")
futoi_stats["last_log_date"] = futoi_date
futoi_stats["last_log_name"] = futoi_log
collectors_info["FutOI"] = futoi_stats
hi2_stats = get_folder_stats(DATA_ROOT / "hi2")
hi2_date, hi2_log = get_last_log_info("hi2_collector")
hi2_stats["last_log_date"] = hi2_date
hi2_stats["last_log_name"] = hi2_log
collectors_info["HI2"] = hi2_stats
funding_file = DATA_ROOT / "funding" / "funding.parquet"
if funding_file.exists():
    df_funding = pd.read_parquet(funding_file)
    funding_date, funding_log = get_last_log_info("funding")
    funding_stats = {"status": "✅", "files": 1, "total_rows": len(df_funding), "last_modified": os.path.getmtime(funding_file), "last_log_date": funding_date, "last_log_name": funding_log}
else:
    funding_stats = {"status": "❌", "files": 0, "total_rows": 0, "last_modified": None, "last_log_date": None, "last_log_name": "нет"}
collectors_info["Funding"] = funding_stats
sc_stats = get_folder_stats(DATA_ROOT / "supercandles")
sc_date, sc_log = get_last_log_info("supercandles_collector")
sc_stats["last_log_date"] = sc_date
sc_stats["last_log_name"] = sc_log
collectors_info["Super Candles"] = sc_stats
h4_stats = get_folder_stats(DATA_ROOT / "supercandles_h4")
h4_date, h4_log = get_last_log_info("supercandles")
h4_stats["last_log_date"] = h4_date
h4_stats["last_log_name"] = h4_log
collectors_info["Super Candles H4"] = h4_stats

# ========== НАСТРОЙКИ СТРАНИЦЫ ==========
st.set_page_config(page_title="FinLabPy Terminal", page_icon="📊", layout="wide", initial_sidebar_state="expanded")

# ========== САЙДБАР ==========
st.sidebar.title("🚀 FinLabPy Terminal")
st.sidebar.markdown("---")
page = st.sidebar.radio("📌 Навигация", ["Дашборд", "FutOI", "Super Candles", "Funding", "Super Candles H4"], index=0)
st.sidebar.markdown("---")
st.sidebar.info("**FinLabPy v0.2.0**\n\nКурс: FutOI + HI2 + ML\n\nСервер: `lvkseaqdin`\nДанные: Parquet")

# ========== РОУТИНГ СТРАНИЦ ==========
if page == "Дашборд":
    st.title("📋 Статус сборщиков")
    st.caption("Данные обновлены с сервера lvkseaqdin")
    cols = st.columns(len(collectors_info))
    for col, (name, info) in zip(cols, collectors_info.items()):
        with col:
            last_mod = "нет"
            if info.get("last_modified"):
                dt = datetime.fromtimestamp(info["last_modified"])
                last_mod = dt.strftime("%d.%m.%Y %H:%M")
            log_info = ""
            if info.get("last_log_date"):
                log_info = f"📋 лог: {info['last_log_date'].strftime('%d.%m.%Y')}"
            st.metric(label=f"{info['status']} {name}", value=f"{info['total_rows']:,}".replace(",", " "), delta=f"📅 {last_mod} {log_info}")
    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("📁 Детали по сборщикам")
        detail_data = []
        for name, info in collectors_info.items():
            last_mod_formatted = "—"
            if info.get("last_modified"):
                dt = datetime.fromtimestamp(info["last_modified"])
                last_mod_formatted = dt.strftime("%d.%m.%Y %H:%M")
            detail_data.append({"Сборщик": name, "Статус": info['status'], "Файлов": info['files'], "Записей": f"{info['total_rows']:,}".replace(",", " "), "Данные от": last_mod_formatted, "Лог": info.get('last_log_name', '—')})
        st.dataframe(pd.DataFrame(detail_data), use_container_width=True, hide_index=True)
    with col2:
        st.subheader("📊 Все Parquet-файлы")
        if DATA_ROOT.exists():
            files = list(DATA_ROOT.rglob("*.parquet"))
            if files:
                df_files = pd.DataFrame([{"Файл": f.relative_to(DATA_ROOT).as_posix(), "Размер (KB)": round(f.stat().st_size / 1024, 1), "Изменён": datetime.fromtimestamp(os.path.getmtime(f)).strftime("%d.%m.%Y %H:%M")} for f in sorted(files)])
                st.dataframe(df_files, use_container_width=True, hide_index=True)
            else:
                st.warning("Parquet-файлы не найдены")
        else:
            st.error(f"Папка {DATA_ROOT} не найдена")

elif page == "FutOI":
    st.title("📈 FutOI — Расширенная аналитика")
    all_data, tickers = load_futoi_data()
    if all_data is None:
        st.error("Данные FutOI не найдены")
    else:
        selected_ticker = st.selectbox("Выберите тикер", tickers)
        df_analytics = prepare_futoi_analytics(all_data[all_data['ticker'] == selected_ticker])
        if df_analytics.empty:
            st.warning(f"Нет данных для {selected_ticker}")
        else:
            candle_file = DATA_ROOT / "candles" / f"{selected_ticker}_D1.parquet"
            df_d1 = pd.read_parquet(candle_file) if candle_file.exists() else None
            tradestats_file = DATA_ROOT / "tradestats" / f"{selected_ticker}_tradestats.parquet"
            df_ts = pd.read_parquet(tradestats_file) if tradestats_file.exists() else None
            atr_info, _ = calculate_atr(df_d1) if df_d1 is not None else (None, None)

            # Загружаем HI2 для вердикта
            hi2_info = None
            hi2_data = load_hi2_data()
            if hi2_data is not None:
                hi2_ticker = hi2_data[hi2_data['ticker'] == selected_ticker]
                if len(hi2_ticker) > 0:
                    hi2_agressive = hi2_ticker[hi2_ticker['metric'] == 'hhi_agressive']
                    if len(hi2_agressive) > 0:
                        hi2_sorted = hi2_agressive.sort_values('tradedate')
                        last_hi2 = hi2_sorted.iloc[-1]
                        hi2_value = last_hi2['value']
                        hi2_delta = None
                        if len(hi2_sorted) >= 2:
                            hi2_delta = hi2_value - hi2_sorted.iloc[-2]['value']
                        
                        # Относительные уровни (процентили от исторического максимума)
                        hi2_max = hi2_sorted['value'].max()
                        hi2_pct = (hi2_value / hi2_max * 100) if hi2_max > 0 else 0
                        
                        if hi2_pct > 75:
                            hi2_level = "Экстремальная"
                            hi2_emoji = "🔴"
                        elif hi2_pct > 50:
                            hi2_level = "Высокая"
                            hi2_emoji = "🟡"
                        elif hi2_pct > 25:
                            hi2_level = "Средняя"
                            hi2_emoji = "🟢"
                        else:
                            hi2_level = "Низкая"
                            hi2_emoji = "🟢"
                        
                        hi2_info = {
                            'value': hi2_value,
                            'level': hi2_level,
                            'emoji': hi2_emoji,
                            'delta': hi2_delta,
                            'pct': hi2_pct,
                            'max': hi2_max
                        }
                        hi2_info = {
                            'value': hi2_value,
                            'level': hi2_level,
                            'emoji': hi2_emoji,
                            'delta': hi2_delta
                        }

            signal_type, signal_info, signal_emoji, signal_history, poc_price, high_20, low_20 = calculate_signals(df_analytics, df_d1, df_ts, atr_info, hi2_info)
            latest = df_analytics.iloc[-1]
            prev = df_analytics.iloc[-2] if len(df_analytics) > 1 else latest

            # === ЛЕВАЯ И ПРАВАЯ КОЛОНКИ ===
            col_left, col_right = st.columns([3, 2])

            with col_left:
                # === МЕТРИКИ НАВЕРХУ ===
                delta_fiz_1h, delta_yur_1h = calculate_delta_1h(df_analytics)
                
                col1, col2, col3 = st.columns(3)
                fiz_long_pct = latest['pos_long_fiz'] / (latest['pos_long_fiz'] + latest['pos_short_fiz'] + 1) * 100
                yur_short_pct = latest['pos_short_yur'] / (latest['pos_long_yur'] + latest['pos_short_yur'] + 1) * 100
                diff_pct = fiz_long_pct - yur_short_pct
                
                if delta_fiz_1h is not None:
                    fiz_arrow = "▲" if delta_fiz_1h > 0.1 else "▼" if delta_fiz_1h < -0.1 else "▬"
                    fiz_delta_str = f"{delta_fiz_1h:+.1f}% за 1 час"
                else:
                    fiz_arrow = ""
                    fiz_delta_str = "нет данных"
                
                if delta_yur_1h is not None:
                    yur_arrow = "▲" if delta_yur_1h > 0.1 else "▼" if delta_yur_1h < -0.1 else "▬"
                    yur_delta_str = f"{delta_yur_1h:+.1f}% за 1 час"
                else:
                    yur_arrow = ""
                    yur_delta_str = "нет данных"
                
                with col1:
                    st.metric("Открытый интерес", f"{abs(latest['phys_net']):,.0f} контрактов".replace(",", " "), delta=f"Физ в лонге: {fiz_long_pct:.1f}% | Юр в шорте: {yur_short_pct:.1f}% | Δ: {diff_pct:+.1f}%")
                with col2:
                    st.metric("% покупателей среди физиков", f"{latest['fiz_buy_ratio']:.1f}% {fiz_arrow}", delta=fiz_delta_str)
                with col3:
                    st.metric("% покупателей среди юриков", f"{latest['yur_buy_ratio']:.1f}% {yur_arrow}", delta=yur_delta_str)
                
                st.markdown("---")
                
                # === ВЕРДИКТ ПОСЛЕ МЕТРИК ===
                st.markdown(signal_info)

            # Мини-график HI2 (загружаем данные здесь)
            hi2_data_graph = load_hi2_data()
            hi2_history = None
            if hi2_data_graph is not None:
                hi2_ticker_graph = hi2_data_graph[hi2_data_graph['ticker'] == selected_ticker]
                if len(hi2_ticker_graph) > 0:
                    hi2_agressive_graph = hi2_ticker_graph[hi2_ticker_graph['metric'] == 'hhi_agressive']
                    if len(hi2_agressive_graph) > 0:
                        hi2_history = hi2_agressive_graph.sort_values('tradedate').tail(20)
            
            if hi2_history is not None and len(hi2_history) > 1:
                with col_left:
                    # Рассчитываем относительные пороги
                    hi2_max_val = hi2_history['value'].max()
                    p25 = hi2_max_val * 0.25
                    p50 = hi2_max_val * 0.50
                    p75 = hi2_max_val * 0.75
                    
                    fig_hi2 = go.Figure()
                    fig_hi2.add_trace(go.Scatter(
                        x=hi2_history['tradedate'],
                        y=hi2_history['value'],
                        mode='lines+markers',
                        name='HI2',
                        line=dict(color='#FFA500', width=2),
                        marker=dict(size=4)
                    ))
                    # Относительные зоны
                    fig_hi2.add_hrect(y0=0, y1=p25, fillcolor="green", opacity=0.1, line_width=0)
                    fig_hi2.add_hrect(y0=p25, y1=p50, fillcolor="yellow", opacity=0.1, line_width=0)
                    fig_hi2.add_hrect(y0=p50, y1=p75, fillcolor="orange", opacity=0.1, line_width=0)
                    fig_hi2.add_hrect(y0=p75, y1=hi2_max_val + 10, fillcolor="red", opacity=0.1, line_width=0)
                    fig_hi2.add_hline(y=p25, line_dash="dash", line_color="green", opacity=0.5)
                    fig_hi2.add_hline(y=p50, line_dash="dash", line_color="red", opacity=0.7)
                    fig_hi2.add_hline(y=p75, line_dash="dash", line_color="darkred", opacity=0.7)
                    fig_hi2.update_layout(
                        title="Концентрация позиций (HI2) за 20 дней",
                        xaxis_title="Дата",
                        yaxis_title="HI2",
                        height=250,
                        template='plotly_dark',
                        margin=dict(l=0, r=0, t=30, b=0)
                    )
                    st.plotly_chart(fig_hi2, use_container_width=True)

            # График D1 справа от вердикта
            if df_d1 is not None:
                with col_right:
                    st.subheader(f"📈 {selected_ticker} (D1)")
                    df_d1['begin'] = pd.to_datetime(df_d1['begin'])
                    df_d1 = df_d1.sort_values('begin')

                    fig_d1 = go.Figure()
                    fig_d1.add_trace(go.Candlestick(
                        x=df_d1['begin'], open=df_d1['open'], high=df_d1['high'],
                        low=df_d1['low'], close=df_d1['close'], name='D1'
                    ))

                    if high_20 is not None:
                        fig_d1.add_hline(y=high_20, line_dash="dash", line_color="red", line_width=2, annotation_text="Сопр.")
                    if low_20 is not None:
                        fig_d1.add_hline(y=low_20, line_dash="dash", line_color="green", line_width=2, annotation_text="Подд.")
                    if poc_price is not None:
                        fig_d1.add_hline(y=poc_price, line_dash="dot", line_color="white", line_width=2, annotation_text="POC")

                    fig_d1.update_layout(
                        title=f"{selected_ticker} с уровнями",
                        xaxis_title="Дата", yaxis_title="Цена",
                        hovermode='x unified', height=500, template='plotly_dark'
                    )
                    st.plotly_chart(fig_d1, use_container_width=True)

            st.markdown("---")

            # График Цена + Позиция (только для акций)
            sc_file = DATA_ROOT / "supercandles" / f"{selected_ticker}_supercandles.parquet"
            if sc_file.exists():
                st.subheader(f"📊 Цена vs Чистая позиция физиков — {selected_ticker}")
                df_price = pd.read_parquet(sc_file)
                df_price['datetime'] = pd.to_datetime(df_price['tradedate'].astype(str) + ' ' + df_price['tradetime'].astype(str))
                fig1 = make_subplots(specs=[[{"secondary_y": True}]])
                fig1.add_trace(go.Scatter(x=df_price['datetime'], y=df_price['pr_close'], mode='lines', name='Цена закрытия', line=dict(color='#FFD700', width=2)), secondary_y=False)
                fig1.add_trace(go.Scatter(x=df_analytics['datetime'], y=df_analytics['phys_net'], mode='lines', name='Чистая позиция физ.', line=dict(color='#00BFFF', width=2)), secondary_y=True)
                fig1.update_layout(title="Цена vs Чистая позиция физиков", hovermode='x unified', height=500, template='plotly_dark')
                fig1.update_yaxes(title_text="Цена", secondary_y=False)
                fig1.update_yaxes(title_text="Позиция", secondary_y=True)
                st.plotly_chart(fig1, use_container_width=True)

            # Volume Profile
            if df_ts is not None:
                st.subheader(f"📊 Volume Profile — {selected_ticker}")
                df_ts['price_level'] = df_ts['pr_close'].round(1)
                vol_profile = df_ts.groupby('price_level').agg(total_vol=('vol', 'sum'), buy_vol=('vol_b', 'sum'), sell_vol=('vol_s', 'sum')).reset_index()
                vol_profile = vol_profile.sort_values('price_level')
                current_price = df_ts['pr_close'].iloc[-1]
                fig_vp = go.Figure()
                fig_vp.add_trace(go.Bar(y=vol_profile['price_level'], x=vol_profile['buy_vol'], orientation='h', name='Покупки', marker_color='green', opacity=0.7))
                fig_vp.add_trace(go.Bar(y=vol_profile['price_level'], x=vol_profile['sell_vol'], orientation='h', name='Продажи', marker_color='red', opacity=0.7))
                fig_vp.add_hline(y=current_price, line_dash="solid", line_color="yellow", line_width=2, annotation_text=f"Цена: {current_price:.2f}")
                fig_vp.update_layout(title=f"Профиль объёма (D1) — {selected_ticker}", xaxis_title="Объём", yaxis_title="Цена", barmode='stack', height=500, template='plotly_dark', showlegend=True)
                st.plotly_chart(fig_vp, use_container_width=True)

            # Графики % покупателей (физики и юрики)
            st.subheader("🎯 Настроение участников")
            
            col_fiz, col_yur = st.columns(2)
            
            with col_fiz:
                current_ratio_fiz = latest['fiz_buy_ratio']
                
                if current_ratio_fiz > 80:
                    st.error(f"🔴 ПЕРЕКУПЛЕННОСТЬ ({current_ratio_fiz:.1f}%)")
                elif current_ratio_fiz < 20:
                    st.success(f"🟢 ПЕРЕПРОДАННОСТЬ ({current_ratio_fiz:.1f}%)")
                elif current_ratio_fiz > 60:
                    st.warning(f"🟡 Выше нормы ({current_ratio_fiz:.1f}%)")
                elif current_ratio_fiz < 40:
                    st.info(f"🔵 Ниже нормы ({current_ratio_fiz:.1f}%)")
                else:
                    st.success(f"⚪ Нейтрально ({current_ratio_fiz:.1f}%)")
                
                fig_fiz = go.Figure()
                fig_fiz.add_trace(go.Scatter(
                    x=df_analytics['datetime'],
                    y=df_analytics['fiz_buy_ratio'],
                    mode='lines',
                    name='% покупателей (Физ)',
                    line=dict(color='#00BFFF', width=2)
                ))
                fig_fiz.add_hrect(y0=80, y1=100, fillcolor="red", opacity=0.1, line_width=0)
                fig_fiz.add_hrect(y0=0, y1=20, fillcolor="green", opacity=0.1, line_width=0)
                fig_fiz.add_hline(y=80, line_dash="dash", line_color="red", opacity=0.5)
                fig_fiz.add_hline(y=20, line_dash="dash", line_color="green", opacity=0.5)
                fig_fiz.add_hline(y=50, line_dash="dot", line_color="gray", opacity=0.3)
                fig_fiz.update_layout(
                    title="% покупателей среди физиков",
                    xaxis_title="Дата",
                    yaxis_title="% покупателей",
                    height=350,
                    template='plotly_dark'
                )
                st.plotly_chart(fig_fiz, use_container_width=True)
            
            with col_yur:
                current_ratio_yur = latest['yur_buy_ratio']
                
                if current_ratio_yur > 80:
                    st.error(f"🔴 ПЕРЕКУПЛЕННОСТЬ ({current_ratio_yur:.1f}%)")
                elif current_ratio_yur < 20:
                    st.success(f"🟢 ПЕРЕПРОДАННОСТЬ ({current_ratio_yur:.1f}%)")
                elif current_ratio_yur > 60:
                    st.warning(f"🟡 Выше нормы ({current_ratio_yur:.1f}%)")
                elif current_ratio_yur < 40:
                    st.info(f"🔵 Ниже нормы ({current_ratio_yur:.1f}%)")
                else:
                    st.success(f"⚪ Нейтрально ({current_ratio_yur:.1f}%)")
                
                fig_yur = go.Figure()
                fig_yur.add_trace(go.Scatter(
                    x=df_analytics['datetime'],
                    y=df_analytics['yur_buy_ratio'],
                    mode='lines',
                    name='% покупателей (Юр)',
                    line=dict(color='#FF6B6B', width=2)
                ))
                fig_yur.add_hrect(y0=80, y1=100, fillcolor="red", opacity=0.1, line_width=0)
                fig_yur.add_hrect(y0=0, y1=20, fillcolor="green", opacity=0.1, line_width=0)
                fig_yur.add_hline(y=80, line_dash="dash", line_color="red", opacity=0.5)
                fig_yur.add_hline(y=20, line_dash="dash", line_color="green", opacity=0.5)
                fig_yur.add_hline(y=50, line_dash="dot", line_color="gray", opacity=0.3)
                fig_yur.update_layout(
                    title="% покупателей среди юриков",
                    xaxis_title="Дата",
                    yaxis_title="% покупателей",
                    height=350,
                    template='plotly_dark'
                )
                st.plotly_chart(fig_yur, use_container_width=True)
elif page == "Super Candles":
    st.title("🕯️ Super Candles (D1)")
    all_data, tickers = load_supercandles_data()
    if all_data is None:
        st.error("Данные Super Candles не найдены")
    else:
        selected_ticker = st.selectbox("Выберите тикер", tickers)
        df_ticker = all_data[all_data["secid"] == selected_ticker].copy()
        df_ticker["datetime"] = pd.to_datetime(df_ticker["tradedate"].astype(str) + " " + df_ticker["tradetime"].astype(str))
        st.subheader(f"Super Candles — {selected_ticker}")
        fig = go.Figure()
        fig.add_trace(go.Candlestick(x=df_ticker["datetime"], open=df_ticker["pr_open"], high=df_ticker["pr_high"], low=df_ticker["pr_low"], close=df_ticker["pr_close"], name="Цена"))
        fig.update_layout(title=f"Super Candles ({selected_ticker})", xaxis_title="Дата", yaxis_title="Цена", hovermode="x unified", height=600, template="plotly_dark")
        st.plotly_chart(fig, use_container_width=True)
        st.subheader("Последние записи")
        st.dataframe(df_ticker.tail(10), use_container_width=True, hide_index=True)

elif page == "Funding":
    st.title("💰 Ставки фандинга")
    funding_path = DATA_ROOT / "funding" / "funding.parquet"
    if funding_path.exists():
        df = pd.read_parquet(funding_path)
        last_date = df['date'].max()
        df_latest = df[df['date'] == last_date].copy()
        st.success(f"Ставки фандинга на {last_date}")
        st.caption(f"Всего записей в базе: {len(df)}")
        st.dataframe(df_latest[['ticker', 'swaprate', 'last_price']], use_container_width=True, hide_index=True)
    else:
        st.error(f"Файл {funding_path} не найден")

elif page == "Super Candles H4":
    st.title("🕯️ Super Candles H4")
    h4_path = DATA_ROOT / "supercandles_h4"
    if h4_path.exists():
        files = list(h4_path.glob("*.parquet"))
        if files:
            st.success(f"Найдено {len(files)} файлов H4")
            sample_file = files[0]
            df = pd.read_parquet(sample_file)
            st.subheader(f"Файл: {sample_file.name}")
            st.dataframe(df.tail(10), use_container_width=True)
        else:
            st.warning("Файлы H4 не найдены")
    else:
        st.error(f"Папка {h4_path} не существует")


















