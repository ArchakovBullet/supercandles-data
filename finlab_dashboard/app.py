import streamlit as st
from pathlib import Path
import pandas as pd
import os
from datetime import datetime
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ========== КОНФИГ ==========
# Путь к данным на сервере
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
    
    return {
        "status": "✅",
        "files": len(parquet_files),
        "total_rows": total_rows,
        "last_modified": last_modified
    }

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
    return all_data, tickers

# ========== ФУНКЦИИ АНАЛИТИКИ FUTOI ==========
def prepare_futoi_analytics(df_ticker):
    """Подготовка данных с аналитикой по физлицам и юрлицам"""
    # Создаём datetime
    df_ticker['datetime'] = pd.to_datetime(
        df_ticker['tradedate'].astype(str) + ' ' + df_ticker['tradetime'].astype(str)
    )
    
    # Разделяем на физиков и юриков
    df_fiz = df_ticker[df_ticker['clgroup'] == 'FIZ'].copy()
    df_yur = df_ticker[df_ticker['clgroup'] == 'YUR'].copy()
    
    # Агрегируем по времени (последняя запись для каждого момента)
    df_fiz = df_fiz.sort_values(['datetime', 'seqnum'])
    df_yur = df_yur.sort_values(['datetime', 'seqnum'])
    
    df_fiz_agg = df_fiz.groupby('datetime').last().reset_index()
    df_yur_agg = df_yur.groupby('datetime').last().reset_index()
    
    # Объединяем в один датафрейм
    df_merged = pd.merge(
        df_fiz_agg[['datetime', 'pos', 'pos_long', 'pos_short', 'pos_long_num', 'pos_short_num']],
        df_yur_agg[['datetime', 'pos', 'pos_long', 'pos_short', 'pos_long_num', 'pos_short_num']],
        on='datetime',
        suffixes=('_fiz', '_yur'),
        how='outer'
    ).sort_values('datetime')
    
    # Заполняем пропуски
    df_merged = df_merged.ffill().fillna(0)
    
    # Расчёт метрик
    df_merged['phys_net'] = df_merged['pos_fiz']
    df_merged['corp_net'] = df_merged['pos_yur']
    
    # % покупателей среди физиков и юриков
    df_merged['fiz_buy_ratio'] = df_merged['pos_long_num_fiz'] / (df_merged['pos_long_num_fiz'] + df_merged['pos_short_num_fiz'] + 1) * 100
    df_merged['yur_buy_ratio'] = df_merged['pos_long_num_yur'] / (df_merged['pos_long_num_yur'] + df_merged['pos_short_num_yur'] + 1) * 100
    
    # Соотношение позиций
    df_merged['fiz_yur_ratio'] = df_merged['phys_net'] / (abs(df_merged['corp_net']) + 1)
    
    # Объём позиций
    df_merged['fiz_volume'] = df_merged['pos_long_fiz'] + df_merged['pos_short_fiz']
    df_merged['yur_volume'] = df_merged['pos_long_yur'] + df_merged['pos_short_yur']
    
    return df_merged

def calculate_signals(df):
    """Расчёт торговых сигналов с контекстным выводом"""
    if len(df) < 3:
        return "NEUTRAL", "Недостаточно данных", "⚪", []
    
    # Рассчитываем сигналы для последних 10 точек
    history = []
    
    for i in range(max(0, len(df) - 10), len(df)):
        if i < 3:
            continue
        
        window = df.iloc[:i+1]
        latest = window.iloc[-1]
        prev = window.iloc[-2]
        
        strength = 0
        
        # 1. Тренд по чистой позиции физиков
        if latest['phys_net'] > prev['phys_net']:
            strength += 1
        elif latest['phys_net'] < prev['phys_net']:
            strength -= 1
        
        # 2. % покупателей среди физиков
        if latest['fiz_buy_ratio'] > 60:
            strength += 1
        elif latest['fiz_buy_ratio'] < 40:
            strength -= 1
        
        # 3. Соотношение физ/юр
        if latest['fiz_yur_ratio'] > 0.5 and latest['phys_net'] > 0:
            strength += 1
        elif latest['fiz_yur_ratio'] < -0.5 and latest['phys_net'] < 0:
            strength -= 1
        
        # Определяем сигнал
        if strength >= 2:
            signal_type = "LONG"
        elif strength <= -2:
            signal_type = "SHORT"
        else:
            signal_type = "NEUTRAL"
        
        # Проверка дивергенции
        divergence = False
        if i >= 5:
            pos_change = latest['phys_net'] - df.iloc[i-3]['phys_net']
            vol_change = latest['fiz_volume'] - df.iloc[i-3]['fiz_volume']
            if (pos_change > 0 and vol_change < 0) or (pos_change < 0 and vol_change > 0):
                divergence = True
        
        history.append({
            'datetime': latest['datetime'],
            'signal': signal_type,
            'strength': strength,
            'divergence': divergence,
            'fiz_buy_ratio': latest['fiz_buy_ratio'],
            'yur_buy_ratio': latest['yur_buy_ratio'],
            'phys_net': latest['phys_net'],
            'corp_net': latest['corp_net'],
            'fiz_yur_ratio': latest['fiz_yur_ratio']
        })
    
    # Текущий сигнал
    if history:
        current = history[-1]
        signal_type = current['signal']
        
        if abs(current['strength']) == 3:
            signal_strength = "СИЛЬНЫЙ"
        elif abs(current['strength']) == 2:
            signal_strength = "СРЕДНИЙ"
        else:
            signal_strength = "СЛАБЫЙ"
        
        signal_emoji = "🟢" if signal_type == "LONG" else "🔴" if signal_type == "SHORT" else "⚪"
        
        # === ФОРМИРОВАНИЕ КОНТЕКСТНОГО ВЫВОДА ===
        lines = []
        
        # Заголовок
        if signal_type == "LONG":
            lines.append(f"**{signal_emoji} Сигнал: ОТКРЫТИЕ ЛОНГА ({signal_strength})**")
        elif signal_type == "SHORT":
            lines.append(f"**{signal_emoji} Сигнал: ОТКРЫТИЕ ШОРТА ({signal_strength})**")
        else:
            lines.append(f"**{signal_emoji} Сигнал: НЕЙТРАЛЬНО ({signal_strength})**")
        
        lines.append("")
        lines.append("**📊 Ситуация:**")
        lines.append(f"- Физики: чистая позиция {current['phys_net']:+,.0f} контрактов".replace(",", " "))
        lines.append(f"- Юрики: чистая позиция {current['corp_net']:+,.0f} контрактов".replace(",", " "))
        lines.append(f"- % покупателей среди физиков: **{current['fiz_buy_ratio']:.1f}%**")
        lines.append(f"- % покупателей среди юриков: **{current['yur_buy_ratio']:.1f}%**")
        
        # Кто давит
        if current['phys_net'] > 0 and current['corp_net'] < 0:
            lines.append(f"- ⚡ Физики покупают, юрики продают — **противоборство**.")
        elif current['phys_net'] > 0 and current['corp_net'] > 0:
            lines.append(f"- ✅ Обе группы в лонге — **единство**.")
        elif current['phys_net'] < 0 and current['corp_net'] > 0:
            lines.append(f"- ⚡ Физики продают, юрики покупают — **противоборство**.")
        elif current['phys_net'] < 0 and current['corp_net'] < 0:
            lines.append(f"- ✅ Обе группы в шорте — **единство**.")
        
        # Давление
        if current['fiz_buy_ratio'] > 60:
            lines.append(f"- 📈 Давление физиков: **покупатели доминируют** ({current['fiz_buy_ratio']:.1f}%)")
        elif current['fiz_buy_ratio'] < 40:
            lines.append(f"- 📉 Давление физиков: **продавцы доминируют** ({current['fiz_buy_ratio']:.1f}%)")
        
        if current['yur_buy_ratio'] > 60:
            lines.append(f"- 📈 Давление юриков: **покупатели доминируют** ({current['yur_buy_ratio']:.1f}%)")
        elif current['yur_buy_ratio'] < 40:
            lines.append(f"- 📉 Давление юриков: **продавцы доминируют** ({current['yur_buy_ratio']:.1f}%)")
        
        lines.append("")
        
        # Риск
        risk = []
        if current['fiz_buy_ratio'] > 80:
            risk.append("🔴 Перекупленность у физиков")
        elif current['fiz_buy_ratio'] < 20:
            risk.append("🟢 Перепроданность у физиков")
        
        if current['yur_buy_ratio'] > 80:
            risk.append("🔴 Перекупленность у юриков")
        elif current['yur_buy_ratio'] < 20:
            risk.append("🟢 Перепроданность у юриков")
        
        if current['divergence']:
            risk.append("⚠️ Дивергенция (объём и позиция расходятся)")
        
        if risk:
            lines.append(f"**⚠️ Риск:** {', '.join(risk)}")
        else:
            lines.append("**✅ Риск:** Низкий. Картина чистая.")
        
        lines.append("")
        
        # Рекомендация
        if signal_type == "LONG":
            if "Перекупленность" in str(risk):
                lines.append("**💡 Рекомендация:** Лонг с уменьшенным объёмом (перекупленность). Ждать отката для входа.")
            else:
                lines.append("**💡 Рекомендация:** Входить в лонг. Физики и юрики поддерживают рост.")
        elif signal_type == "SHORT":
            if "Перепроданность" in str(risk):
                lines.append("**💡 Рекомендация:** Шорт с уменьшенным объёмом (перепроданность). Ждать отскока для входа.")
            else:
                lines.append("**💡 Рекомендация:** Входить в шорт. Физики и юрики поддерживают падение.")
        else:
            lines.append("**💡 Рекомендация:** Ждать. Сигнал не сформирован. Наблюдать за изменением позиций.")
        
        # Смена сигнала
        if len(history) >= 3:
            last_signals = [h['signal'] for h in history[-3:]]
            prev_signal = last_signals[-2]
            if last_signals[-1] != prev_signal:
                lines.append("")
                prev_emoji = "🟢" if prev_signal == "LONG" else "🔴" if prev_signal == "SHORT" else "⚪"
                lines.append(f"🔄 **Смена сигнала:** предыдущий был {prev_emoji} {prev_signal}")
        
        signal_info = "\n".join(lines)
    else:
        signal_type = "NEUTRAL"
        signal_info = "Недостаточно данных"
        signal_emoji = "⚪"
    
    return signal_type, signal_info, signal_emoji, history

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
    funding_stats = {
        "status": "✅",
        "files": 1,
        "total_rows": len(df_funding),
        "last_modified": os.path.getmtime(funding_file),
        "last_log_date": funding_date,
        "last_log_name": funding_log
    }
else:
    funding_stats = {
        "status": "❌", 
        "files": 0, 
        "total_rows": 0, 
        "last_modified": None,
        "last_log_date": None,
        "last_log_name": "нет"
    }
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
st.set_page_config(
    page_title="FinLabPy Terminal",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ========== САЙДБАР ==========
st.sidebar.title("🚀 FinLabPy Terminal")
st.sidebar.markdown("---")

page = st.sidebar.radio(
    "📌 Навигация",
    ["Дашборд", "FutOI", "Super Candles", "Funding", "Super Candles H4"],
    index=0
)

st.sidebar.markdown("---")
st.sidebar.info(
    "**FinLabPy v0.2.0**\n\n"
    "Курс: FutOI + HI2 + ML\n\n"
    "Сервер: lvkseaqdin\n"
    "Данные: Parquet"
)

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
            
            st.metric(
                label=f"{info['status']} {name}",
                value=f"{info['total_rows']:,}".replace(",", " "),
                delta=f"📅 {last_mod} {log_info}"
            )
    
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
            
            detail_data.append({
                "Сборщик": name,
                "Статус": info['status'],
                "Файлов": info['files'],
                "Записей": f"{info['total_rows']:,}".replace(",", " "),
                "Данные от": last_mod_formatted,
                "Лог": info.get('last_log_name', '—')
            })
        st.dataframe(pd.DataFrame(detail_data), use_container_width=True, hide_index=True)
    
    with col2:
        st.subheader("📊 Все Parquet-файлы")
        if DATA_ROOT.exists():
            files = list(DATA_ROOT.rglob("*.parquet"))
            if files:
                df_files = pd.DataFrame([
                    {
                        "Файл": f.relative_to(DATA_ROOT).as_posix(), 
                        "Размер (KB)": round(f.stat().st_size / 1024, 1),
                        "Изменён": datetime.fromtimestamp(os.path.getmtime(f)).strftime("%d.%m.%Y %H:%M")
                    }
                    for f in sorted(files)
                ])
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
        
        # Получаем расширенную аналитику
        df_analytics = prepare_futoi_analytics(all_data[all_data['ticker'] == selected_ticker])
        
        if df_analytics.empty:
            st.warning(f"Нет данных для {selected_ticker}")
        else:
            # Сигналы
            signal_type, signal_info, signal_emoji, signal_history = calculate_signals(df_analytics)
            
            # Последние значения
            latest = df_analytics.iloc[-1]
            prev = df_analytics.iloc[-2] if len(df_analytics) > 1 else latest
            
            # Блок сигнала с контекстом
            st.markdown(f"## {signal_emoji} Текущий сигнал: {signal_type}")
            st.markdown(signal_info)
            
            # Основные метрики
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric(
                    "Чистая позиция физиков",
                    f"{latest['phys_net']:+,.0f}".replace(",", " "),
                    delta=f"{(latest['phys_net'] - prev['phys_net']):+,.0f}".replace(",", " ")
                )
            
            with col2:
                st.metric(
                    "Чистая позиция юриков",
                    f"{latest['corp_net']:+,.0f}".replace(",", " "),
                    delta=f"{(latest['corp_net'] - prev['corp_net']):+,.0f}".replace(",", " ")
                )
            
            with col3:
                st.metric(
                    "% покупателей среди физиков",
                    f"{latest['fiz_buy_ratio']:.1f}%",
                    delta=f"{(latest['fiz_buy_ratio'] - prev['fiz_buy_ratio']):+.1f}%"
                )
            
            with col4:
                st.metric(
                    "% покупателей среди юриков",
                    f"{latest['yur_buy_ratio']:.1f}%",
                    delta=f"{(latest['yur_buy_ratio'] - prev['yur_buy_ratio']):+.1f}%"
                )
            
            st.markdown("---")
            
            # График Цена + Позиция (только для акций)
            sc_file = DATA_ROOT / "supercandles" / f"{selected_ticker}_supercandles.parquet"
            
            if sc_file.exists():
                st.subheader(f"📊 Цена vs Чистая позиция физиков — {selected_ticker}")
                
                df_price = pd.read_parquet(sc_file)
                df_price['datetime'] = pd.to_datetime(
                    df_price['tradedate'].astype(str) + ' ' + df_price['tradetime'].astype(str)
                )
                
                fig1 = make_subplots(specs=[[{"secondary_y": True}]])
                
                # Цена
                fig1.add_trace(
                    go.Scatter(
                        x=df_price['datetime'],
                        y=df_price['pr_close'],
                        mode='lines',
                        name='Цена закрытия',
                        line=dict(color='#FFD700', width=2)
                    ),
                    secondary_y=False
                )
                
                # Чистая позиция физиков
                fig1.add_trace(
                    go.Scatter(
                        x=df_analytics['datetime'],
                        y=df_analytics['phys_net'],
                        mode='lines',
                        name='Чистая позиция физ.',
                        line=dict(color='#00BFFF', width=2)
                    ),
                    secondary_y=True
                )
                
                fig1.update_layout(
                    title="Цена vs Чистая позиция физиков (дивергенция = расхождение линий)",
                    hovermode='x unified',
                    height=500,
                    template='plotly_dark'
                )
                
                fig1.update_yaxes(title_text="Цена", secondary_y=False)
                fig1.update_yaxes(title_text="Позиция", secondary_y=True)
                
                st.plotly_chart(fig1, use_container_width=True)
            
            # Индикаторы настроения (для всех)
            st.subheader("🎯 Индикаторы настроения")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("### Физики")
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
                
                # График % покупателей физиков с зонами
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
            
            with col2:
                st.markdown("### Юрики")
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
                
                # График % покупателей юриков с зонами
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
            
            # История сигналов
            st.subheader("📜 История сигналов (последние 5)")
            
            if signal_history:
                history_df = pd.DataFrame(signal_history[-5:])
                history_df = history_df.rename(columns={
                    'datetime': 'Время',
                    'signal': 'Сигнал',
                    'fiz_buy_ratio': '% покуп. физ',
                    'divergence': 'Дивергенция'
                })
                
                # Добавляем эмодзи к сигналам
                history_df['Сигнал'] = history_df['Сигнал'].map({
                    'LONG': '🟢 LONG',
                    'SHORT': '🔴 SHORT',
                    'NEUTRAL': '⚪ NEUTRAL'
                })
                
                st.dataframe(
                    history_df[['Время', 'Сигнал', '% покуп. физ', 'Дивергенция']],
                    use_container_width=True,
                    hide_index=True
                )
                
                # Анализ последовательности
                if len(signal_history) >= 3:
                    last_signals = [h['signal'] for h in signal_history[-3:]]
                    if last_signals[-1] != last_signals[-2]:
                        st.info("🔄 Последний сигнал изменился! Проверьте графики для подтверждения.")
            
            # Таблица последних значений
            st.subheader("Последние 10 наблюдений")
            display_cols = ['datetime', 'phys_net', 'corp_net', 'fiz_buy_ratio', 'yur_buy_ratio', 'fiz_yur_ratio']
            display_df = df_analytics[display_cols].tail(10).sort_values('datetime', ascending=False)
            
            display_df = display_df.rename(columns={
                'datetime': 'Дата',
                'phys_net': 'Чистая физ.',
                'corp_net': 'Чистая юр.',
                'fiz_buy_ratio': '% покуп. физ',
                'yur_buy_ratio': '% покуп. юр',
                'fiz_yur_ratio': 'Соотн. физ/юр'
            })
            
            st.dataframe(display_df, use_container_width=True, hide_index=True)

elif page == "Super Candles":
    st.title("🕯️ Super Candles (D1)")
    
    all_data, tickers = load_supercandles_data()
    
    if all_data is None:
        st.error("Данные Super Candles не найдены")
    else:
        selected_ticker = st.selectbox("Выберите тикер", tickers)
        
        df_ticker = all_data[all_data["secid"] == selected_ticker].copy()
        
        df_ticker["datetime"] = pd.to_datetime(
            df_ticker["tradedate"].astype(str) + " " + df_ticker["tradetime"].astype(str)
        )
        
        st.subheader(f"Super Candles — {selected_ticker}")
        
        fig = go.Figure()
        
        fig.add_trace(go.Candlestick(
            x=df_ticker["datetime"],
            open=df_ticker["pr_open"],
            high=df_ticker["pr_high"],
            low=df_ticker["pr_low"],
            close=df_ticker["pr_close"],
            name="Цена"
        ))
        
        fig.update_layout(
            title=f"Super Candles ({selected_ticker})",
            xaxis_title="Дата",
            yaxis_title="Цена",
            hovermode="x unified",
            height=600,
            template="plotly_dark"
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
        st.subheader("Последние записи")
        st.dataframe(df_ticker.tail(10), use_container_width=True, hide_index=True)

elif page == "Funding":
    st.title("💰 Ставки фандинга")
    
    funding_path = DATA_ROOT / "funding" / "funding.parquet"
    if funding_path.exists():
        df = pd.read_parquet(funding_path)
        st.success(f"Загружено {len(df)} записей")
        st.dataframe(df.tail(20), use_container_width=True)
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

