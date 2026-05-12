import streamlit as st
from pathlib import Path
import pandas as pd
import os
from datetime import datetime
import plotly.graph_objects as go

# ========== КОНФИГ ==========
DATA_ROOT = Path(__file__).parent.parent / "Data"
LOGS_ROOT = Path(__file__).parent.parent / "logs"

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

# ========== ЗАГРУЗКА ДАННЫХ FUTOI ==========
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
    ["Дашборд", "FutOI", "Funding", "Super Candles H4"],
    index=0
)

st.sidebar.markdown("---")
st.sidebar.info(
    "**FinLabPy v0.1.0**\n\n"
    "Курс: FutOI + HI2 + ML\n\n"
    "Сервер: lvkseaqdin\n"
    "Данные: Parquet"
)

# ========== РОУТИНГ СТРАНИЦ ==========
if page == "Дашборд":
    st.title("📋 Статус сборщиков")
    st.caption("Реальные данные из файловой системы (обновлено 12.05.2026)")
    
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
    st.title("📈 FutOI — чистая позиция физиков")
    
    all_data, tickers = load_futoi_data()
    
    if all_data is None:
        st.error("Данные FutOI не найдены")
    else:
        selected_ticker = st.selectbox("Выберите тикер", tickers)
        
        # Фильтрация данных
        df_ticker = all_data[all_data['ticker'] == selected_ticker].copy()
        
        # Только физики
        df_fiz = df_ticker[df_ticker['clgroup'] == 'FIZ'].copy()
        
        if df_fiz.empty:
            st.warning(f"Нет данных по физикам для {selected_ticker}")
        else:
            # Создаём datetime
            df_fiz['datetime'] = pd.to_datetime(
                df_fiz['tradedate'].astype(str) + ' ' + df_fiz['tradetime'].astype(str)
            )
            
            # АГРЕГАЦИЯ: берём последнюю запись для каждого момента времени
            # Группируем по времени и берём последнюю по seqnum
            df_fiz = df_fiz.sort_values(['datetime', 'seqnum'])
            df_agg = df_fiz.groupby('datetime').last().reset_index()
            
            # Пересчитываем изменения на основе агрегированных данных
            if len(df_agg) >= 2:
                latest = df_agg.iloc[-1]
                prev = df_agg.iloc[-2]
                
                pos_change = latest['pos'] - prev['pos']
                long_change = latest['pos_long'] - prev['pos_long']
                short_change = latest['pos_short'] - prev['pos_short']
            else:
                latest = df_agg.iloc[-1]
                pos_change = 0
                long_change = 0
                short_change = 0
            
            # Метрики
            col1, col2, col3 = st.columns(3)
            
            with col1:
                signal = "🟢 ЛОНГ" if latest['pos'] > 0 else "🔴 ШОРТ"
                st.metric(
                    f"Чистая позиция физиков {signal}",
                    f"{latest['pos']:,.0f}".replace(",", " "),
                    delta=f"{pos_change:+,.0f}".replace(",", " ")
                )
            
            with col2:
                st.metric(
                    "Длинные позиции",
                    f"{latest['pos_long']:,.0f}".replace(",", " "),
                    delta=f"{long_change:+,.0f}".replace(",", " ")
                )
            
            with col3:
                st.metric(
                    "Короткие позиции",
                    f"{latest['pos_short']:,.0f}".replace(",", " "),
                    delta=f"{short_change:+,.0f}".replace(",", " ")
                )
            
            st.markdown("---")
            
            # График
            st.subheader(f"График чистой позиции (phys_net) — {selected_ticker}")
            
            fig = go.Figure()
            
            fig.add_trace(go.Scatter(
                x=df_agg['datetime'],
                y=df_agg['pos'],
                mode='lines+markers',
                name='Чистая позиция',
                line=dict(color='#00BFFF', width=2),
                marker=dict(size=4),
                fill='tozeroy',
                fillcolor='rgba(0,191,255,0.1)'
            ))
            
            fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)
            
            fig.update_layout(
                title=f"Динамика чистой позиции физиков ({selected_ticker})",
                xaxis_title="Дата",
                yaxis_title="Позиция (контрактов)",
                hovermode='x unified',
                height=500,
                template='plotly_dark',
                margin=dict(l=0, r=0, t=40, b=0)
            )
            
            st.plotly_chart(fig, use_container_width=True)
            
            # Таблица последних значений (агрегированная, без индекса)
            st.subheader("Последние 10 наблюдений")
            display_cols = ['datetime', 'pos', 'pos_long', 'pos_short', 'pos_long_num', 'pos_short_num']
            display_df = df_agg[display_cols].tail(10).sort_values('datetime', ascending=False)
            
            # Переименовываем колонки для красоты
            display_df = display_df.rename(columns={
                'datetime': 'Дата',
                'pos': 'Чистая поз.',
                'pos_long': 'Лонги',
                'pos_short': 'Шорты',
                'pos_long_num': 'Кол-во лонг',
                'pos_short_num': 'Кол-во шорт'
            })
            
            st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True
            )

elif page == "Funding":
    st.title("💰 Ставки фандинга")
    st.info("Загрузка данных фандинга...")
    
    funding_path = DATA_ROOT / "funding" / "funding.parquet"
    if funding_path.exists():
        df = pd.read_parquet(funding_path)
        st.success(f"Загружено {len(df)} записей")
        st.dataframe(df.tail(20), use_container_width=True)
    else:
        st.error(f"Файл {funding_path} не найден")

elif page == "Super Candles H4":
    st.title("🕯️ Super Candles H4")
    st.info("Загрузка агрегированных данных H4...")
    
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
