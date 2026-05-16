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
    return all_data, tickers

# ========== ФУНКЦИИ АНАЛИТИКИ FUTOI ==========
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

