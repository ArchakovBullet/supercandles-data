
import streamlit as st
from pathlib import Path
import pandas as pd
import os
import json
from datetime import datetime
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import sys
sys.path.insert(0, '/root/finlab/FinLabPy')
from My_Indicators.short_signal import ShortSignalAnalyzer
from My_Indicators.garch_indicator import calculate_garch_for_ticker
from My_Indicators.market_aggression import calculate_aggression_for_ticker
from My_Indicators.robot_classifier import classify_market
from My_Indicators.cross_market import analyze_cross_market
from My_Indicators.advanced_levels import calculate_advanced_levels
from My_Indicators.advanced_levels_1h import calculate_advanced_levels_1h
from My_Indicators.risk_manager import calculate_risk
from My_Indicators.aggression_1h import calculate_aggression_1h
from My_Indicators.order_flow_imbalance import calculate_ofi
from My_Indicators.cumulative_delta import calculate_cumulative_delta
from pathlib import Path
from My_Indicators.stock_screener import screen_stocks
from My_Indicators.stock_scanner_tf import get_stock_scanner_verdict
from My_Indicators.sector_analysis import analyze_vs_sector
from My_Indicators.market_regime import get_market_regime
from My_Indicators.trading_session import get_session_status
from My_Indicators.herrick_payoff_index import calculate_hpi
from My_Indicators.arms_index import calculate_trin
from My_Indicators.zweig_filter import get_zweig_signal
from My_Indicators.mega_alerts import get_mega_alerts
from My_Indicators.unified_verdict import get_unified_verdict
from My_Indicators.unified_scanner import get_unified_scanner_verdict
from My_Indicators.unified_scanner import get_unified_scanner_verdict
from My_Indicators.pairs_trading import analyze_pair
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
    max_age_days = 0
    now = datetime.now()
    for f in parquet_files:
        try:
            df = pd.read_parquet(f)
            total_rows += len(df)
            mtime = os.path.getmtime(f)
            if last_modified is None or mtime > last_modified:
                last_modified = mtime
            # Проверяем возраст файла
            age_days = (now - datetime.fromtimestamp(mtime)).days
            if age_days > max_age_days:
                max_age_days = age_days
        except Exception as e:
            st.warning(f"Ошибка чтения {f.name}: {e}")
    # Определяем статус по возрасту (по последнему обновлению, а не самому старому файлу)
    age_of_newest = (now - datetime.fromtimestamp(last_modified)).days if last_modified else 999
    if age_of_newest > 3:
        status = "🔴"
    elif age_of_newest > 1:
        status = "🟡"
    else:
        status = "✅"
    return {"status": status, "files": len(parquet_files), "total_rows": total_rows, "last_modified": last_modified, "age_days": age_of_newest}
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

def load_stock_tickers():
    """Загрузить список акций из tickers_config.json"""
    import json
    cfg_path = Path('/root/finlab/FinLabPy/DataCollectors/tickers_config.json')
    if cfg_path.exists():
        with open(cfg_path, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        return cfg.get('stocks', ['SBER', 'GAZP', 'GMKN', 'LKOH', 'HYDR', 'IRAO', 'PLZL', 'ROSN', 'TATN', 'VTBR', 'AFKS', 'T', 'AFLT', 'YDEX'])
    return ['SBER', 'GAZP', 'GMKN', 'LKOH', 'HYDR', 'IRAO', 'PLZL', 'ROSN', 'TATN', 'VTBR', 'AFKS', 'T', 'AFLT', 'YDEX']

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
    # Костыль: нормализуем тикеры (Si -> SI и т.д.)
    _ticker_fix = {'Si': 'SI', 'Br': 'BR', 'Gd': 'GD', 'Ri': 'RI', 'Pt': 'PT', 'Vi': 'VI', 'Mx': 'MX', 'Ed': 'ED'}
    all_data['ticker'] = all_data['ticker'].replace(_ticker_fix)
    tickers = sorted(all_data['ticker'].unique(), key=lambda t: (t not in ['CNYRUBF','GAZPF','GLDRUBF','IMOEXF','SBERF','USDRUBF','EURRUBF'], t))
    return all_data, tickers
@st.cache_data
def get_ticker_verdict(ticker):
    """Возвращает готовый вердикт для тикера (используется в сканере и сводке)."""
    try:
        futoi_file = DATA_ROOT / "futoi" / f"{ticker}_futoi.parquet"
        d1_file = DATA_ROOT / "candles" / f"{ticker}_D1.parquet"
        ts_file = DATA_ROOT / "tradestats" / f"{ticker}_tradestats.parquet"
        
        if not futoi_file.exists() or not d1_file.exists():
            return None
        
        df_futoi = pd.read_parquet(futoi_file)
        df_d1 = pd.read_parquet(d1_file)
        df_ts = pd.read_parquet(ts_file) if ts_file.exists() else None
        
        # Подготавливаем аналитику
        df_analytics = prepare_futoi_analytics(df_futoi)
        if df_analytics.empty:
            return None
        
        # ATR
        atr_info, _ = calculate_atr(df_d1)
        
        # HI2
        hi2_info = None
        hi2_data = load_hi2_data()
        if hi2_data is not None:
            hi2_ticker = hi2_data[hi2_data['ticker'] == ticker]
            if len(hi2_ticker) > 0:
                hi2_agressive = hi2_ticker[hi2_ticker['metric'] == 'hhi_agressive']
                if len(hi2_agressive) > 0:
                    hi2_sorted = hi2_agressive.sort_values('tradedate')
                    hi2_value = hi2_sorted.iloc[-1]['value']
                    if hi2_value > 500: hi2_emoji = "🔴"
                    elif hi2_value > 150: hi2_emoji = "🔴"
                    elif hi2_value > 70: hi2_emoji = "🟡"
                    elif hi2_value > 40: hi2_emoji = "🟢"
                    else: hi2_emoji = "🟢"
                    hi2_info = {'value': hi2_value, 'emoji': hi2_emoji, 'level': 'Нет данных', 'delta': None}
        
        _hi2_stub = hi2_info if hi2_info else {'value': 0, 'emoji': '—', 'level': 'Нет данных', 'delta': None}
        
        # Сигналы
        signal_type, signal_info, signal_emoji, signal_history, poc_price, high_20, low_20 = calculate_signals(
            df_analytics, df_d1, df_ts, atr_info, _hi2_stub
        )
        
        # Шорт-скор
        _short_score = 50
        if "SHORT" in signal_type:
            _short_score = 60 if "BLOCKED" in signal_type else 85
        elif "LONG" in signal_type:
            _short_score = 40 if "BLOCKED" in signal_type else 15
        
        # OFI и Cumulative Delta
        _ofi = calculate_ofi(df_ts) if df_ts is not None else None
        _cd = calculate_cumulative_delta(df_ts) if df_ts is not None else None
        
        # Тренд
        _trend_up = False
        _trend_down = False
        if len(df_d1) >= 20:
            df_d1['sma20'] = df_d1['close'].rolling(20).mean()
            _last = df_d1['close'].iloc[-1]
            _sma = df_d1['sma20'].iloc[-1]
            if _last > _sma * 1.02: _trend_up = True
            elif _last < _sma * 0.98: _trend_down = True
        
        _atr = atr_info['atr'] if atr_info else None
        _close = df_d1['close'].iloc[-1]
        
        # RVI из секторов
        _garch_vol = 0
        try:
            _rvi_f = DATA_ROOT / "sector_indices" / "RVI_D1.parquet"
            if _rvi_f.exists():
                _rvi_df = pd.read_parquet(_rvi_f)
                if len(_rvi_df) > 0 and 'close' in _rvi_df.columns:
                    _garch_vol = _rvi_df['close'].iloc[-1]  # Приводим к процентам
        except:
            pass
        
        # Загружаем 4H и 1H данные (как в сканере)
        _df_4h = None
        _df_1h = None
        _h4_file = DATA_ROOT / 'futoi_4h' / 'futoi_4h.parquet'
        _h1_file = DATA_ROOT / 'futoi_1h' / 'futoi_1h.parquet'
        if _h4_file.exists():
            try:
                _df_4h_all = pd.read_parquet(_h4_file)
                _df_4h = _df_4h_all[_df_4h_all['ticker'] == ticker].sort_values('hour')
            except:
                pass
        if _h1_file.exists():
            try:
                _df_1h_all = pd.read_parquet(_h1_file)
                _df_1h = _df_1h_all[_df_1h_all['ticker'] == ticker].sort_values('hour')
            except:
                pass

        # Используем unified_scanner для получения 4H/1H сигналов
        # Volume spike
        _vol_spike = False
        try:
            from My_Indicators.volume_analyzer import VolumeAnomalyDetector
            _vd = VolumeAnomalyDetector()
            _vdf = pd.read_parquet(DATA_ROOT / 'candles' / f'{ticker}_D1.parquet')
            if 'volume' in _vdf.columns and len(_vdf) > 25:
                _spikes = _vd.detect_spikes(_vdf['volume'])
                _vol_spike = bool(_spikes['spikes'].iloc[-1])
        except:
            pass

        # RVI для кризисного режима
        _rvi_val = None
        try:
            _rvi_file = DATA_ROOT / 'sector_indices' / 'RVI_D1.parquet'
            if not _rvi_file.exists():
                _rvi_file = DATA_ROOT / 'candles' / 'RVI_D1.parquet'
            if _rvi_file.exists():
                _rvi_df = pd.read_parquet(_rvi_file)
                if len(_rvi_df) > 0:
                    _rvi_val = _rvi_df['close'].iloc[-1]
        except:
            pass

        _scanner_result = get_unified_scanner_verdict(
            df_analytics, _df_4h, _df_1h,
            d1_trend_up=_trend_up, d1_trend_down=_trend_down,
            hi2_value=hi2_info['value'] if hi2_info else None,
            garch_vol=_garch_vol,
            ofi=_ofi, cum_delta=_cd,
            volume_spike=_vol_spike,
            rvi_val=_rvi_val
        )

        # Вердикт (с HI2-штрафом)
        _uni = get_unified_verdict(
            signal_type, _short_score, _ofi, _cd,
            _trend_up, _trend_down,
            None, None, _atr, _close,
            hi2_value=hi2_info['value'] if hi2_info else None
        )
        
        # Тренд для отображения
        if _trend_up: _trend_str = "📈 Бычий"
        elif _trend_down: _trend_str = "📉 Медвежий"
        else: _trend_str = "◼ Боковик"
        
        # Сигналы по ТФ (берём из unified_scanner)
        _s1d = _scanner_result['signals']['1D']['signal']
        _s4h = _scanner_result['signals']['4H']['signal']
        _s1h = _scanner_result['signals']['1H']['signal']

        return {
            'ticker': ticker,
            'decision': _scanner_result['decision'],
            'crisis_mode': _scanner_result.get('crisis_mode', False),
            'score': _scanner_result['score'],
            'confidence': _scanner_result['confidence'],
            'recommendation': _scanner_result['recommendation'],
            'long_score': _scanner_result['score'] if _scanner_result['decision'] == 'LONG' else (100 - _scanner_result['score'] if _scanner_result['decision'] == 'SHORT' else 50),
            'short_score': _scanner_result['score'] if _scanner_result['decision'] == 'SHORT' else (100 - _scanner_result['score'] if _scanner_result['decision'] == 'LONG' else 50),
            'reason': _scanner_result['recommendation'],
            'entry_price': _uni['entry_price'],
            'stop_loss': _uni['stop_loss'],
            'target': _uni['target'],
            'trend': _trend_str,
            'hi2_value': hi2_info['value'] if hi2_info else None,
            'garch_vol': _garch_vol,
            'close': _close,
            'fiz_buy': df_analytics.iloc[-1].get('fiz_buy_ratio', 50),
            'signal_1d': _s1d,
            'signal_4h': _s4h,
            'signal_1h': _s1h,
        }
    except Exception as e:
        import traceback
        print(f"ERROR get_ticker_verdict({ticker}): {e}")
        traceback.print_exc()
        return None


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
@st.cache_data
def load_futoi_1h_data():
    """Загружает 1H данные FutOI."""
    f = DATA_ROOT / "futoi_1h" / "futoi_1h.parquet"
    if not f.exists():
        return None, []
    df = pd.read_parquet(f)
    tickers = sorted(df["ticker"].unique())
    return df, tickers
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
            'fiz_yur_ratio': latest['fiz_yur_ratio'], 'fiz_volume': latest['fiz_volume'], 'yur_volume': latest['yur_volume'],
            'pos_short_yur': latest.get('pos_short_yur', 0), 'pos_long_yur': latest.get('pos_long_yur', 0),
            'close': latest.get('close', 0), 'atr': latest.get('atr', 0)
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
    
    # Расширенный шорт-анализ
    show_short = signal_type in ("SHORT", "BLOCKED_SHORT", "WAIT_FOR_BOUNCE", "NEUTRAL")
    if not show_short:
        reasons_str = ", ".join(block_reasons) if block_reasons else ""
        if signal_type == "BLOCKED_LONG" and "Дистрибуция" in reasons_str:
            show_short = True
        if signal_type == "WAIT_FOR_RETRACEMENT":
            show_short = True  # Всегда показываем шорт-анализ при перегретости
        if signal_type == "NEUTRAL" and is_distribution:
            show_short = True
    if show_short:
        try:
            analyzer = ShortSignalAnalyzer(st.session_state.get('selected_ticker', 'SBERF'))
            jur_sell_for_net = 100 - current.get('yur_buy_ratio', 50)
            if 'pos_short_yur' in current:
                total_yur = current.get('pos_short_yur', 0) + current.get('pos_long_yur', 1)
                if total_yur > 0:
                    jur_sell_for_net = current['pos_short_yur'] / total_yur * 100
            net = analyzer.calculate_net_positions(
                current.get('fiz_buy_ratio', 50),
                jur_sell_for_net
            )
            lines.append("")
            lines.append("**📉 ШОРТ-АНАЛИЗ (ShortSignalAnalyzer):**")
            lines.append(f"- Чистая позиция физиков: {net['phys_net']:+.1f}% — {net['phys_verdict']}")
            lines.append(f"- Чистая позиция юриков: {net['jur_net']:+.1f}% — {net['jur_verdict']}")
            
            score, verdict, reasons_list = analyzer.get_short_score(
                jur_pct_sell=jur_sell_for_net,
                phys_pct_buy=current.get('fiz_buy_ratio', 50),
                price_vs_poc=-1,
                volatility_percent=0.8,
                trend='боковик'
            )
            lines.append(f"- Шорт-скор: {score:.0f}/100 — {verdict}")
            if reasons_list:
                lines.append(f"- Причины: {'; '.join(reasons_list[:3])}")
            
            # Расчёт рисков — берём реальные цену и ATR из current
            entry_price = last_close if 'last_close' in dir() else 320.32
            atr = current.get('atr', 2.56)
            if atr == 0:
                atr = abs(entry_price * 0.008)  # 0.8% от цены как запасной вариант
            
            risk = analyzer.calculate_risk(
                entry_price=entry_price,
                atr=atr,
                capital=100000,
                risk_percent=2.0
            )
            lines.append(f"- Стоп-лосс: {risk['stop_loss']:.2f} (+{risk['risk_per_unit']:.2f})")
            lines.append(f"- Риск на сделку: {risk['max_risk_rub']:,.0f} ₽ ({risk['max_risk_pct']}% от депозита)")
            lines.append(f"- Размер позиции: {risk['position_size']} контрактов")
            lines.append(f"- Выход: по противоположному сигналу (LONG)")
        except Exception as e:
            lines.append(f"*⚠️ Ошибка шорт-анализа: {e}*")
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
            try:
                garch_result = calculate_garch_for_ticker(df_d1, selected_ticker) if df_d1 is not None else {}
                garch_vol = garch_result.get('garch_vol')
                if garch_vol:
                    garch_trend = garch_result.get('trend', '—')
                    lines.append(f"| GARCH (годовая) | {garch_vol:.1f}% {garch_trend} |")
            except:
                pass
        delta_str = ""
        if hi2_info is not None:
            delta_str = ""
            if hi2_info['delta'] is not None:
                arrow = "▲" if hi2_info['delta'] > 0 else "▼"
                delta_str = f" ({arrow} {abs(hi2_info['delta']):.0f} за сутки)"
                    # Агрессивность рынка
            try:
                ts_path = DATA_ROOT / 'tradestats' / f'{selected_ticker}_tradestats.parquet'
                ts_df = pd.read_parquet(ts_path) if ts_path.exists() else None
                agg_result = calculate_aggression_for_ticker(ts_df, df_d1, hi2_info['value'] if hi2_info else None, selected_ticker)
                if agg_result and agg_result['level'] != 'Нет данных':
                    lines.append(f"| Агрессивность | {agg_result['score']:.0f}/100 — {agg_result['level']} ({agg_result['direction']} активнее) |")
            except Exception as e:
                pass
            
                # Типы алгоритмов
    try:
        phys_net_val = net.get('phys_net', 0) if 'net' in dir() else 0
        jur_net_val = net.get('jur_net', 0) if 'net' in dir() else 0
        robots = classify_market(
            selected_ticker,
            hi2_info['value'] if hi2_info else 0,
            ts_df if 'ts_df' in dir() else None,
            df_d1,
            phys_net_val,
            jur_net_val
        )
        if robots and robots.get('dominant'):
            lines.append("")
            lines.append("**🤖 ТИПЫ АЛГОРИТМОВ:**")
            for rtype in ['hft', 'vwap', 'iceberg', 'institutional']:
                if robots[rtype]['active']:
                    emoji = {'hft': '⚡', 'vwap': '📊', 'iceberg': '🧊', 'institutional': '🏦'}.get(rtype, '•')
                    lines.append(f"- {emoji} {robots[rtype]['desc']}")
            lines.append(f"- 🎯 Доминируют: {robots['dominant']}")
    except:
        pass
    
    # Кросс-рыночный контекст
    try:
        cross = analyze_cross_market(selected_ticker, df_d1)
        if cross['available']:
            lines.append("")
            lines.append(f"**🔗 КРОСС-РЫНОК ({cross['pair_desc']}):**")
            lines.append(f"- Корреляция с {cross['pair']}: {cross['correlation']:.2f}")
            lines.append(f"- Спред: {cross['spread_direction']} (Z={cross['spread_zscore']})")
            lines.append(f"- Сигнал: {cross['signal']}")
    except:
        pass
        delta_str = ""
    lines.append(f"| HI2 (концентрация) | {hi2_info["value"]:.0f} — {hi2_info["emoji"]} {hi2_info["level"]}{delta_str if "delta_str" in locals() else ""} |")
    lines.append(f"| HI2 (концентрация) | {hi2_info['value']:.0f} — {hi2_info['emoji']} {hi2_info['level']} |")
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
    if hi2_info is not None and hi2_info['level'] in ["Высокая", "Очень высокая", "Экстремальная"]:
        lines.append(f"")
        if hi2_info['level'] == "Экстремальная":
            lines.append(f"**🔍 HI2 = {hi2_info['value']:.0f} (экстремальная концентрация):** Практически весь объём позиций сконцентрирован в руках 1-2 крупных игроков. Рынок полностью зависит от их действий. Любой сигнал может быть ложным, если крупный игрок решит развернуть позицию.")
        elif hi2_info['level'] == "Очень высокая":
            lines.append(f"**🔍 HI2 = {hi2_info['value']:.0f} (очень высокая концентрация):** Несколько крупных игроков контролируют большую часть позиций. Высокий риск резких движений при входе/выходе крупного игрока.")
        else:
            lines.append(f"**🔍 HI2 = {hi2_info['value']:.0f} (высокая концентрация):** Группа крупных игроков контролирует значительную часть позиций. Возможны резкие движения при изменении их стратегии.")
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
    if hi2_info is not None and hi2_info['level'] in ["Высокая", "Очень высокая", "Экстремальная"]:
        risk.append(f"Концентрация {hi2_info['level'].lower()} (HI2={hi2_info['value']:.0f})")
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
tradestats_stats = get_folder_stats(DATA_ROOT / "tradestats")
tradestats_date, tradestats_log = get_last_log_info("tradestats_collector")
tradestats_stats["last_log_date"] = tradestats_date
tradestats_stats["last_log_name"] = tradestats_log
collectors_info["TradeStats"] = tradestats_stats
candles_stats = get_folder_stats(DATA_ROOT / "candles")
candles_date, candles_log = get_last_log_info("candles_collector")
candles_stats["last_log_date"] = candles_date
candles_stats["last_log_name"] = candles_log
collectors_info["Candles"] = candles_stats
futoi1h_stats = get_folder_stats(DATA_ROOT / "futoi_1h")
futoi1h_date, futoi1h_log = get_last_log_info("futoi_1h")
futoi1h_stats["last_log_date"] = futoi1h_date
futoi1h_stats["last_log_name"] = futoi1h_log
collectors_info["FutOI 1H"] = futoi1h_stats
futoi4h_stats = get_folder_stats(DATA_ROOT / "futoi_4h")
futoi4h_date, futoi4h_log = get_last_log_info("futoi_4h")
futoi4h_stats["last_log_date"] = futoi4h_date
futoi4h_stats["last_log_name"] = futoi4h_log
collectors_info["FutOI 4H"] = futoi4h_stats
sector_stats = get_folder_stats(DATA_ROOT / "sector_indices")
sector_date, sector_log = get_last_log_info("sector_indices")
sector_stats["last_log_date"] = sector_date
sector_stats["last_log_name"] = sector_log
collectors_info["Сектора"] = sector_stats
# ========== НАСТРОЙКИ СТРАНИЦЫ ==========
st.set_page_config(page_title="FinLabPy Terminal", page_icon="📊", layout="wide", initial_sidebar_state="expanded")

# === АВТООБНОВЛЕНИЕ СТРАНИЦЫ (каждые 4 часа) ===
AUTO_REFRESH_SECONDS = 14400  # 4 часа
if 'page_refreshed' not in st.session_state:
    st.session_state['page_refreshed'] = False

# Проверяем, было ли автообновление
if st.session_state.get('codes_updated'):
    st.session_state['page_refreshed'] = True

# Живой счётчик автообновления
import streamlit.components.v1 as components
components.html(f'''
<meta http-equiv="refresh" content="{AUTO_REFRESH_SECONDS}">
<style>
  .refresh-counter {{ font-size: 0.8em; color: #888; margin-bottom: 8px; }}
</style>
<div class="refresh-counter">
🔄 Автообновление через <span id="refresh-counter">{AUTO_REFRESH_SECONDS // 60}:00</span>
</div>
<script>
let seconds = {AUTO_REFRESH_SECONDS};
const counter = document.getElementById('refresh-counter');
setInterval(() => {{
    seconds--;
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    counter.textContent = mins + ':' + (secs < 10 ? '0' : '') + secs;
    if (seconds <= 0) seconds = {AUTO_REFRESH_SECONDS};
}}, 1000);
</script>
''', height=30)
# ========== САЙДБАР ==========
st.sidebar.title("🚀 FinLabPy Terminal")
st.sidebar.markdown('<style>[data-testid="stSidebar"] .stMarkdown { margin-bottom: -35px; } [data-testid="stSidebar"] .stMetric { margin-top: -35px; }</style>', unsafe_allow_html=True)
st.sidebar.markdown("---")
st.sidebar.markdown("---")
st.sidebar.subheader("💰 Риск-менеджмент")
_deposit = st.sidebar.number_input("Депозит (₽)", min_value=10000, value=100000, step=10000, format="%d")
_risk_pct = st.sidebar.slider("Риск на сделку (%)", min_value=0.1, max_value=5.0, value=1.0, step=0.1)

with st.sidebar.expander("ℹ️ Как это работает?"):
    st.markdown("""
**Калькулятор позиции** рассчитывает количество контрактов на основе:
- **Депозита** — ваш торговый капитал
- **Риска на сделку (%)** — максимальный убыток в % от депозита
- **Расстояния до стоп-лосса** — разница между ценой входа и стопом

**Формула:**
`Риск в рублях = Депозит × Риск% / 100`
`Контрактов = Риск в рублях / (Расстояние до стопа × Лот)`

**Пример:**
- Депозит: 100 000 ₽, Риск: 1% → Риск = 1 000 ₽
- Вход: 113.52, Стоп: 112.65 → Расстояние = 0.87
- Лот GAZPF = 10 → Риск на контракт = 8.7 ₽
- Позиция = 1 000 / 8.7 = 114 контрактов

**Лоты:**
- CNYRUBF, USDRUBF, EURRUBF = 1000
- Остальные = 10
    """)

st.sidebar.markdown("---")

page = st.sidebar.radio("📌 Навигация", ["📊 Сводка", "📋 Статус сборщиков", "📊 Сканер фьючерсов", "📊 Парная торговля", "📊 Скринер акций", "🔧 Техинфо"], index=0)
st.sidebar.markdown("---")
st.sidebar.info("**FinLabPy v0.2.0**\n\nКурс: FutOI + HI2 + ML\n\nСервер: `lvkseaqdin`\nДанные: Parquet")
# ========== РОУТИНГ СТРАНИЦ ==========
if page == "📊 Сводка":
    st.title("📊 Сводка — сигналы на вход")
    st.caption("Быстрый обзор рынка — все фьючерсы")
    
    # === ТЕМПЕРАТУРА РЫНКА ===
    with st.expander("🌡️ Температура рынка (фьючерсы)", expanded=True):
        st.caption("IMOEX + RVI + RGBI + сектора + RVI/ADX/Choppiness фьючерсов")
        # === 1. IMOEX ===
        _imoex_trend = None
        _imoex_file = DATA_ROOT / "sector_indices" / "IMOEX_D1.parquet"
        if _imoex_file.exists():
            _imoex_df = pd.read_parquet(_imoex_file)
            if len(_imoex_df) >= 20:
                _imoex_df['sma20'] = _imoex_df['close'].rolling(20).mean()
                _imoex_last = _imoex_df['close'].iloc[-1]
                _imoex_sma = _imoex_df['sma20'].iloc[-1]
                if _imoex_last > _imoex_sma * 1.02:
                    _imoex_trend = "UP"
                elif _imoex_last < _imoex_sma * 0.98:
                    _imoex_trend = "DOWN"
                else:
                    _imoex_trend = "FLAT"

        # === 2. RGBI ===
        _rgbi_change = 0
        _rgbi_file = DATA_ROOT / "sector_indices" / "RGBI_D1.parquet"
        if _rgbi_file.exists():
            _rgbi_df = pd.read_parquet(_rgbi_file)
            if len(_rgbi_df) >= 5:
                _rgbi_change = (_rgbi_df['close'].iloc[-1] - _rgbi_df['close'].iloc[-5]) / _rgbi_df['close'].iloc[-5] * 100

        # === 3. Сектора ===
        _sector_change = 0
        _sector_count = 0
        for _si in ['MOEXMM', 'MOEXFN', 'MOEXOG', 'MOEXEU', 'MOEXTL']:
            _sf = DATA_ROOT / "sector_indices" / f"{_si}_D1.parquet"
            if _sf.exists():
                _sdf = pd.read_parquet(_sf)
                if len(_sdf) >= 5:
                    _sector_change += (_sdf['close'].iloc[-1] - _sdf['close'].iloc[-5]) / _sdf['close'].iloc[-5] * 100
                    _sector_count += 1
        _avg_sector_change = _sector_change / _sector_count if _sector_count > 0 else 0

        # RVI из секторов (единый для всех)
        _garch_vals = []
        _adx_vals = []
        _chop_vals = []
        _rvi_val = None

        _rvi_f = DATA_ROOT / "sector_indices" / "RVI_D1.parquet"
        if _rvi_f.exists():
            _rvi_df = pd.read_parquet(_rvi_f)
            if len(_rvi_df) > 0 and 'close' in _rvi_df.columns:
                _rvi_val = _rvi_df['close'].iloc[-1]
                _garch_vals.append(_rvi_val)

        _avg_garch = sum(_garch_vals) / len(_garch_vals) if _garch_vals else 0
        
        # Собираем ADX/Choppiness по фьючерсам
        _adx_vals = []
        _chop_vals = []
        try:
            from My_Indicators.stock_screener import calculate_adx, calculate_choppiness
            for _t in _all_futures:
                _d1f = DATA_ROOT / "candles" / f"{_t}_D1.parquet"
                if _d1f.exists():
                    _df = pd.read_parquet(_d1f)
                    if len(_df) >= 30:
                        _adx_vals.append(calculate_adx(_df).iloc[-1])
                        _chop_vals.append(calculate_choppiness(_df).iloc[-1])
        except:
            pass
        
        _avg_adx = sum(_adx_vals) / len(_adx_vals) if _adx_vals else 0
        _avg_chop = sum(_chop_vals) / len(_chop_vals) if _chop_vals else 50
        
        _df_indices = pd.DataFrame({'adx': [_avg_adx], 'choppiness': [_avg_chop]}) if _adx_vals else None
        
        # RVI
        _rvi_val = None
        _rvi_file = DATA_ROOT / "sector_indices" / "RVI_D1.parquet"
        if _rvi_file.exists():
            _rvi_df = pd.read_parquet(_rvi_file)
            if len(_rvi_df) > 0:
                _rvi_val = _rvi_df['close'].iloc[-1]
        
        _regime = get_market_regime(df_indices=_df_indices, garch_vol=_rvi_val if _rvi_val else 15, rvi_val=_rvi_val, imoex_trend=_imoex_trend, rgbi_change=_rgbi_change, avg_sector_change=_avg_sector_change)
        
        _emoji = "🚀" if _regime['regime'] == 'TREND' else "🔄" if _regime['regime'] == 'FLAT' else "🌪️" if _regime['regime'] == 'CRISIS' else "⚠️"
        
        col_t1, col_t2, col_t3 = st.columns(3)
        with col_t1:
            st.metric("Режим", f"{_emoji} {_regime['regime']}", delta=f"Скор: {_regime['score']}/100")
        with col_t2:
            st.metric("Уровень риска", f"{_regime['risk_level']}/100")
        with col_t3:
            st.metric("RVI (индекс волатильности, пункты)", f"{_avg_garch:.1f} п.")
        
        _session = get_session_status()
        st.caption(f"📊 Сессия: {_session['label']} | Ликвидность: {_session['liquidity']:.0%}")
        if _session['warning']:
            st.warning(f"⚠️ {_session['warning']}")
        
        with st.expander("ℹ️ О торговых сессиях"):
            st.markdown("""
**Время торгов на MOEX (МСК):**
| Период | Время | Ликвидность | Особенности |
|--------|-------|:---:|-----------|
| Основная сессия | 10:00–18:45 | 🟢 Высокая | Лучшее время для входа |
| Открытие | 10:00–10:30 | 🟡 Средняя | Высокая волатильность, ложные пробои |
| Обед | 12:00–13:00 | 🔴 Низкая | Мало объёмов, сигналы могут быть ложными |
| Закрытие | 18:30–18:45 | 🟡 Средняя | Закрытие позиций, резкие движения |
| Вечерняя сессия | 19:00–23:50 | 🔴 Низкая | Широкие спреды, низкая ликвидность |

**Рекомендации:**
- 🟢 Входить только в активную сессию (10:30–12:00, 13:00–18:30)
- 🟡 На открытии/закрытии — увеличить стоп на 50%
- 🔴 В обед и вечером — воздержаться от входа или уменьшить позицию вдвое
            """)
        
        st.caption(_regime['recommendation'])
        if _regime['reasons']:
            for _r in _regime['reasons']:
                st.caption(f"• {_r}")
        
        # === ZWEIG MASTER FILTER (ФЬЮЧЕРСЫ) ===
        _session_fut = get_session_status()
        _zweig_fut = get_zweig_signal(_regime, None, _session_fut, _avg_garch)
        st.markdown("---")
        st.subheader(f"{_zweig_fut['emoji']} {_zweig_fut['label']}")
        for _r in _zweig_fut['reasons']:
            st.caption(f"• {_r}")
        
        with st.expander("ℹ️ Что это значит?"):
            st.markdown("""
**Температура рынка** — объективная оценка на основе индексов MOEX и технических индикаторов.

**Источники:**
- **IMOEX** — индекс МосБиржи (тренд рынка)
- **RVI** — индекс волатильности (>40 = паника)
- **RGBI** — индекс облигаций (переток капитала)
- **Сектора** — MOEXOG, MOEXFN, MOEXMM, MOEXEU, MOEXTL
- **RVI** — индекс волатильности рынка
- **ADX / Choppiness** — сила и направленность тренда

**Три режима:**
- 🚀 **TREND** — можно торговать по сигналам
- 🔄 **FLAT** — не входить, ждать пробоя
- 🌪️ **CRISIS** — RVI>40%. Запрет входа. Подробнее в сканере фьючерсов (🌪️ Что такое КРИЗИС-РЕЖИМ?)

**Уровень риска:** 0 = безопасно, 100 = максимальный риск.
            """)
    
    # Получаем вердикты через единую функцию (как в сканере)
    _all_data, _all_tickers = load_futoi_data()
    TICKERS = _all_tickers if _all_tickers else ["CNYRUBF", "GAZPF", "GLDRUBF", "IMOEXF", "SBERF", "USDRUBF", "EURRUBF", "BR"]

    rows = []
    for ticker in TICKERS:
        _v = get_ticker_verdict(ticker)
        if _v is None:
            continue
        
        _d1_sig = _v['signal_1d']
        _d1_emoji = "🟢" if "LONG" in str(_d1_sig) else ("🔴" if "SHORT" in str(_d1_sig) else "⚪")
        _4h_sig = _v['signal_4h']
        _4h_emoji = "🟢" if "LONG" in str(_4h_sig) else ("🔴" if "SHORT" in str(_4h_sig) else "⚪")
        _1h_sig = _v['signal_1h']
        _1h_emoji = "🟢" if "LONG" in str(_1h_sig) else ("🔴" if "SHORT" in str(_1h_sig) else "⚪")
        
        # Рекомендация на основе decision и signal_1d
        _dec = _v['decision']
        _sig = str(_v['signal_1d'])
        if _dec == 'LONG' and 'WAIT' not in _sig:
            _rec = "✅ Вход в лонг"
        elif _dec == 'SHORT' and 'WAIT' not in _sig:
            _rec = "✅ Вход в шорт"
        elif _dec == 'LONG' and 'WAIT' in _sig:
            _rec = "⏳ Ждать отката (лонг)"
        elif _dec == 'SHORT' and 'WAIT' in _sig:
            _rec = "⏳ Ждать отскока (шорт)"
        else:
            _rec = "⏳ Ждать"
        
        rows.append({
            "Тикер": ticker,
            "Цена": f"{_v['close']:.2f}" if _v['close'] else "—",
            "D1": f"{_d1_emoji} {_d1_sig}",
            "4H": f"{_4h_emoji} {_4h_sig}",
            "1H": f"{_1h_emoji} {_1h_sig}",
            "fiz %": f"{_v['fiz_buy']:.1f}",
            "Тренд": _v['trend'],
            "HI2": f"{_v['hi2_value']:.0f}" if _v['hi2_value'] else "—",
            "GARCH": f"{_v['garch_vol']:.1f}%" if _v['garch_vol'] else "—",
            "Лонг": f"{_v['long_score']}/100" if _v['long_score'] != 50 or _v['short_score'] != 50 else "—",
            "Шорт": f"{_v['short_score']}/100" if _v['long_score'] != 50 or _v['short_score'] != 50 else "—",
            "Рекомендация": _rec,
        })

    if rows:
        df_summary = pd.DataFrame(rows)

        _show_all = st.checkbox("Показать все тикеры", value=False, key="summary_show_all")
        if not _show_all:
            _entry_mask = df_summary["Рекомендация"].str.contains("Вход", na=False)
            df_summary = df_summary[_entry_mask]
            if len(df_summary) == 0:
                st.info("ℹ️ Нет тикеров с сигналом на вход. Все тикеры в режиме ожидания.")
            else:
                st.success(f"🎯 Найдено {len(df_summary)} тикер(ов) с сигналом на вход")
        else:
            st.caption(f"Показаны все {len(df_summary)} тикеров")

        def color_signal(val):
            if 'LONG' in str(val): return 'background-color: rgba(0,255,0,0.2); color: #00ff00; font-weight: bold'
            elif 'SHORT' in str(val): return 'background-color: rgba(255,0,0,0.2); color: #ff4444; font-weight: bold'
            elif 'WAIT' in str(val) or 'NEUTRAL' in str(val): return 'background-color: rgba(128,128,128,0.2); color: #aaaaaa'
            return ''

        def color_recommendation(val):
            if 'Вход' in str(val): return 'background-color: rgba(0,255,0,0.15); font-weight: bold'
            elif 'Не входить' in str(val): return 'background-color: rgba(255,0,0,0.15); font-weight: bold'
            elif 'Перегреты' in str(val) or 'Перепроданы' in str(val): return 'background-color: rgba(255,255,0,0.15)'
            return ''

        styled = df_summary.style.map(color_signal, subset=["D1", "4H", "1H"]).map(color_recommendation, subset=["Рекомендация"])
        st.dataframe(styled, use_container_width=True, hide_index=True)

        
        with st.expander("🔍 Как формируется вердикт и скор?"):
            st.markdown("""
**Факторы (0-100):**
| Фактор | Вес | Описание |
|--------|-----|----------|
| FutOI | 40% | Главный фильтр: позиции физиков/юриков |
| TradeStats | 30% | Шорт-скор: сила сигнала |
| Order Flow | 20% | OFI + Cumulative Delta |
| Тренд | 10% | Контекст рынка (SMA20) |
| HI2 | штраф до -15 | Концентрация позиций |

**Блокировка:** BLOCKED -> WAIT. Перекупленность/перепроданность ослабляют сигнал.

**Уровни:** 🔥95+ | ✅80+ | 👀60+ | ⏳40+ | ❌<40
            """)
    else:
        st.error("Нет данных для отображения")
    
    # === БЛОК АКЦИЙ В СВОДКЕ ===
    st.markdown("---")
    st.subheader("📊 Акции — сигналы на вход")

    _stock_tickers = load_stock_tickers()
    _stock_rows = []

    for _st in _stock_tickers:
        try:
            _sd1 = DATA_ROOT / "candles" / f"{_st}_D1.parquet"
            if not _sd1.exists():
                continue
            _sdf = pd.read_parquet(_sd1)
            if len(_sdf) < 20:
                continue
            _close = _sdf['close'].iloc[-1]

            # HI2 для акции
            _hi2_val = None
            _hi2_file = DATA_ROOT / "hi2" / f"{_st}_hi2.parquet"
            if _hi2_file.exists():
                _df_hi2 = pd.read_parquet(_hi2_file)
                _hi2_agr = _df_hi2[_df_hi2['metric'] == 'hhi_agressive']
                if len(_hi2_agr) > 0:
                    _hi2_val = _hi2_agr.sort_values('tradedate').iloc[-1]['value']

            # Комбинированный сигнал: HI2 + ADX + тренд
            _combo_signal = "⚪ —"
            try:
                from My_Indicators.stock_screener import calculate_adx
                _adx_series = calculate_adx(_sdf.copy())
                _adx_val = _adx_series.iloc[-1] if len(_adx_series) > 0 else 0
                _sma20 = _sdf['close'].rolling(20).mean().iloc[-1]
                _close_val = _sdf['close'].iloc[-1]
                _trend_up = _close_val > _sma20 * 1.02
                _trend_down = _close_val < _sma20 * 0.98
                
                _score = 0
                if _hi2_val and _hi2_val > 500: _score -= 1  # Высокая концентрация = осторожно
                if _adx_val > 25: _score += 1  # Сильный тренд
                if _trend_up: _score += 1
                if _trend_down: _score -= 1
                
                if _score >= 2:
                    _combo_signal = "🟢 LONG"
                elif _score <= -1:
                    _combo_signal = "🔴 SHORT"
            except:
                pass

            # Вердикт через stock_scanner_tf
            from My_Indicators.stock_scanner_tf import get_stock_scanner_verdict
            # Volume spike для акции
            _vol_sp = False
            try:
                from My_Indicators.volume_analyzer import VolumeAnomalyDetector
                _vd_s = VolumeAnomalyDetector()
                if 'volume' in _sdf.columns and len(_sdf) > 25:
                    _sp = _vd_s.detect_spikes(_sdf['volume'])
                    _vol_sp = bool(_sp['spikes'].iloc[-1])
            except:
                pass
            _stock_v = get_stock_scanner_verdict(_sdf.copy(), None, None, _hi2_val, 0, volume_spike=_vol_sp)
            _decision = _stock_v['decision']
            _d1_sig = _stock_v['signals']['1D']['signal']

            _rec = "⏳ Ждать"
            if _decision == 'LONG': _rec = "✅ Вход в лонг"
            elif _decision == 'SHORT': _rec = "✅ Вход в шорт"

            _stock_rows.append({
                "Тикер": _st,
                "Цена": f"{_close:.2f}",
                "Сигнал": _combo_signal,
                "1D": _d1_sig,
                "HI2": f"{_hi2_val:.0f}" if _hi2_val else "—",
                "Рекомендация": _rec,
            })
        except Exception as e:
            pass

    if _stock_rows:
        _df_stocks = pd.DataFrame(_stock_rows)
        _show_all_s = st.checkbox("Показать все акции", value=False, key="stock_show_all")
        if not _show_all_s:
            _entry_s = _df_stocks['Рекомендация'].str.contains('Вход', na=False)
            _df_stocks = _df_stocks[_entry_s]
            if len(_df_stocks) == 0:
                st.info("ℹ️ Нет акций с сигналом на вход.")
            else:
                st.success(f"🎯 Найдено {len(_df_stocks)} акций с сигналом на вход")
        else:
            st.caption(f"Показаны все {len(_df_stocks)} акций")
        st.dataframe(_df_stocks, use_container_width=True, hide_index=True)

    st.markdown("---")


if page == "📋 Статус сборщиков":
    st.title("📋 Статус сборщиков")
    st.caption("Данные обновлены с сервера lvkseaqdin")
    
    with st.expander("ℹ️ Что означают эти данные?", expanded=False):
        st.markdown("""
**Сборщики данных** — это автоматизированные процессы, которые собирают рыночные данные с Московской биржи (MOEX) через Algopack API. Они являются фундаментом для всего анализа в дашборде.

**Какие данные собираются:**

| Сборщик | Что собирает | Где используется |
|---------|-------------|-------------------|
| **FutOI** | Открытый интерес фьючерсов (позиции физиков и юриков) | FutOI (D1), FUTOI_1H — вердикты, дистрибуция/аккумуляция |
| **HI2** | Индекс рыночной концентрации (акции и фьючерсы) | Оценка рисков, сила тренда, уровни поддержки/сопротивления |
| **Funding** | Ставки фандинга | Оценка настроения рынка |
| **Super Candles** | Дневные свечи с объёмами покупок/продаж (только для акций) | Order Flow Imbalance, Cumulative Delta, скринер акций |
| **Super Candles H4** | 4-часовые свечи | Анализ внутридневной динамики |

**Как часто обновляются:**
- FutOI: каждый час
- HI2: раз в день
- Funding: раз в день
- Super Candles: каждые 10 минут
- Super Candles H4: раз в день (агрегация)

**Статусы:**
- ✅ — данные свежие, сборщик работает
- ⚠️ — данные устарели (сборщик не запускался)
- ❌ — ошибка сбора

**Время последнего обновления** показывает, когда были получены последние данные. Если время сильно отстаёт от текущего — сборщик нужно перезапустить.
        """)
    
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
    
    # === ДОБАВЛЕНИЕ НОВОГО ТИКЕРА В FUTOI ===
    with st.expander("➕ Добавить тикер в FutOI (вечные и срочные фьючерсы, индексы)", expanded=False):
        st.markdown("""
        **При добавлении тикера он автоматически появится в:**
        - FutOI и FUTOI_1H (сборщики + аналитика)
        - Сводке (общая таблица)
        - VK-боте (команда «сводка»)
        - Будут собраны: D1/H1 свечи, HI2, TradeStats
        
        **Типы активов:**
        - Вечный фьючерс (RFUD) — CNYRUBF, SBERF, GAZPF и др.
        - Срочный фьючерс (RFUD) — RVI, BR и др.
        - Индекс (INDEX) — IMOEX
        """)
        
        if 'add_ticker_error' in st.session_state:
            st.warning(st.session_state['add_ticker_error'])
            if st.button('✕ Скрыть', key='hide_error'):
                del st.session_state['add_ticker_error']
                st.rerun()
        col_type, col_ticker = st.columns([1, 2])
        with col_type:
            _asset_type = st.selectbox("Тип актива", ["Вечный фьючерс", "Срочный фьючерс", "Индекс"], key="futoi_type")
        with col_ticker:
            _new_futoi_ticker = st.text_input("Тикер", placeholder="Например: NVTKF", key="futoi_ticker").upper()
        
        if st.button("✅ Добавить в FutOI", key="futoi_add_btn"):
            if _new_futoi_ticker:
                try:
                    _board = "RFUD" if _asset_type != "Индекс" else "INDEX"
                    
                    # 1. Собираем D1 и H1 свечи
                    import requests
                    from datetime import datetime, timedelta
                    for _tf, _interval in [("D1", 24), ("H1", 60)]:
                        _url = f"https://iss.moex.com/iss/engines/stock/markets/shares/boards/{_board}/securities/{_new_futoi_ticker}/candles.json"
                        if _board == "RFUD":
                            _url = f"https://iss.moex.com/iss/engines/futures/markets/forts/securities/{_new_futoi_ticker}/candles.json"
                        elif _board == "INDEX":
                            _url = f"https://iss.moex.com/iss/engines/stock/markets/index/securities/{_new_futoi_ticker}/candles.json"
                        
                        _resp = requests.get(_url, params={
                            'from': (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d'),
                            'till': datetime.now().strftime('%Y-%m-%d'),
                            'interval': _interval
                        })
                        if _resp.status_code == 200 and 'candles' in _resp.json():
                            _data = _resp.json()['candles']
                            if _data['data']:
                                _df_new = pd.DataFrame(_data['data'], columns=_data['columns'])
                                _f = DATA_ROOT / "candles" / f"{_new_futoi_ticker}_{_tf}.parquet"
                                _df_new.to_parquet(_f, index=False)
                    
                    # 2. Добавляем в futoi_collector
                    _futoi_conf = Path('/root/finlab/FinLabPy/DataCollectors/futoi_collector.py')
                    with open(_futoi_conf) as f:
                        _fc = f.read()
                    if _new_futoi_ticker not in _fc:
                        _fc = _fc.replace("TICKERS = [", f"TICKERS = ['{_new_futoi_ticker}', ")
                        with open(_futoi_conf, 'w') as f:
                            f.write(_fc)
                    
                    # 3. Добавляем в futoi_1h_aggregator
                    _f1h_conf = Path('/root/finlab/FinLabPy/DataCollectors/futoi_1h_aggregator.py')
                    with open(_f1h_conf) as f:
                        _f1hc = f.read()
                    if _new_futoi_ticker not in _f1hc:
                        _f1hc = _f1hc.replace('TICKERS = [', f"TICKERS = ['{_new_futoi_ticker}', ")
                        with open(_f1h_conf, 'w') as f:
                            f.write(_f1hc)
                    
                    # 4. Добавляем в hi2_collector
                    _hi2_conf = Path('/root/finlab/FinLabPy/DataCollectors/hi2_collector.py')
                    with open(_hi2_conf) as f:
                        _hc = f.read()
                    _engine = 'futures' if _asset_type != 'Индекс' else 'stocks'
                    if f"'{_new_futoi_ticker}': '{_engine}'" not in _hc:
                        _hc = _hc.replace("'GLDRUBF': 'futures'", f"'{_new_futoi_ticker}': '{_engine}', 'GLDRUBF': 'futures'")
                        with open(_hi2_conf, 'w') as f:
                            f.write(_hc)
                    
                    # 5. Добавляем в tradestats_collector
                    _ts_conf = Path('/root/finlab/FinLabPy/DataCollectors/tradestats_collector.py')
                    with open(_ts_conf) as f:
                        _tsc = f.read()
                    _section = 'FUTURES' if _asset_type != 'Индекс' else 'STOCKS'
                    if _new_futoi_ticker not in _tsc:
                        if _section == 'FUTURES':
                            _tsc = _tsc.replace("FUTURES = [", f"FUTURES = ['{_new_futoi_ticker}', ")
                        else:
                            _tsc = _tsc.replace("STOCKS = [", f"STOCKS = ['{_new_futoi_ticker}', ")
                        with open(_ts_conf, 'w') as f:
                            f.write(_tsc)
                    
                    # 6. Добавляем в Сводку (app_v2.py)
                    _app_conf = Path('/root/finlab/finlab_dashboard/app_v2.py')
                    with open(_app_conf) as f:
                        _ac = f.read()
                    _old_tickers = 'TICKERS = ["CNYRUBF", "GAZPF", "GLDRUBF", "IMOEXF", "SBERF", "USDRUBF", "EURRUBF", "BR"]'
                    if _new_futoi_ticker not in _ac:
                        _ac = _ac.replace(_old_tickers, _old_tickers.replace(']', f', "{_new_futoi_ticker}"]'))
                        with open(_app_conf, 'w') as f:
                            f.write(_ac)
                    
                    # 7. Добавляем в VK-бота
                    _vk_conf = Path('/root/finlab/vk_bot.py')
                    with open(_vk_conf) as f:
                        _vc = f.read()
                    if _new_futoi_ticker not in _vc:
                        _vc = _vc.replace("TICKERS = ['GLDRUBF'", f"TICKERS = ['{_new_futoi_ticker}', 'GLDRUBF'")
                        with open(_vk_conf, 'w') as f:
                            f.write(_vc)
                    
                    # 8. Запускаем сборщики
                    import subprocess
                    _venv = '/root/finlab/venv/bin/python'
                    subprocess.run([_venv, '/root/finlab/FinLabPy/DataCollectors/futoi_collector.py'], capture_output=True)
                    subprocess.run([_venv, '/root/finlab/FinLabPy/DataCollectors/futoi_1h_aggregator.py'], capture_output=True)
                    subprocess.run([_venv, '/root/finlab/FinLabPy/DataCollectors/hi2_collector.py'], capture_output=True)
                    subprocess.run([_venv, '/root/finlab/FinLabPy/DataCollectors/tradestats_collector.py'], capture_output=True)
                    
                    st.success(f"✅ {_new_futoi_ticker} добавлен во все системы! Обновите страницу.")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Ошибка: {e}")
    
    st.markdown("---")
    

    if 'codes_update_errors' in st.session_state and st.session_state['codes_update_errors']:
        with st.expander(f'⚠️ Ошибки обновления кодов ({len(st.session_state["codes_update_errors"])} тикеров)', expanded=False):
            for _err in st.session_state['codes_update_errors']:
                st.caption(f'• {_err}')
        if st.button('✕ Скрыть', key='hide_code_errors'):
            del st.session_state['codes_update_errors']
            st.rerun()

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
            hi2_value = None
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
                        if hi2_value > 500:
                            hi2_level = "Экстремальная"
                            hi2_emoji = "🔴"
                        elif hi2_value > 150:
                            hi2_level = "Очень высокая"
                            hi2_emoji = "🔴"
                        elif hi2_value > 70:
                            hi2_level = "Высокая"
                            hi2_emoji = "🟡"
                        elif hi2_value > 40:
                            hi2_level = "Средняя"
                            hi2_emoji = "🟢"
                        else:
                            hi2_level = "Низкая"
                            hi2_emoji = "🟢"
                        hi2_info = {
                            'value': hi2_value,
                            'level': hi2_level,
                            'emoji': hi2_emoji,
                            'delta': hi2_delta
                        }
            _hi2_stub = hi2_info if hi2_info else {'value': 0, 'level': 'Нет данных', 'emoji': '—', 'delta': None}
            signal_type, signal_info, signal_emoji, signal_history, poc_price, high_20, low_20 = calculate_signals(df_analytics, df_d1, df_ts, atr_info, _hi2_stub)
            latest = df_analytics.iloc[-1]
            prev = df_analytics.iloc[-2] if len(df_analytics) > 1 else latest
            # === 🎯 ОБЪЕДИНЁННОЕ РЕШЕНИЕ ===
            # Оценка шорт-скора на основе signal_type
            _short_score = 50
            if "SHORT" in signal_type:
                if "BLOCKED" in signal_type:
                    _short_score = 60
                else:
                    _short_score = 85
            elif "LONG" in signal_type:
                if "BLOCKED" in signal_type:
                    _short_score = 40
                else:
                    _short_score = 15
            # Иначе остаётся 50 (нейтрально)
            
            # Получаем OFI и Cumulative Delta
            _ofi = calculate_ofi(df_ts) if df_ts is not None else None
            _cd = calculate_cumulative_delta(df_ts) if df_ts is not None else None
            
            # Определяем тренд
            _trend_up = False
            _trend_down = False
            if df_d1 is not None and len(df_d1) >= 20:
                if 'sma20' not in df_d1.columns:
                    df_d1['sma20'] = df_d1['close'].rolling(20).mean()
                _last = df_d1['close'].iloc[-1]
                _sma = df_d1['sma20'].iloc[-1]
                if _last > _sma * 1.02: _trend_up = True
                elif _last < _sma * 0.98: _trend_down = True
            
            # Получаем поддержку/сопротивление
            _support = adv_levels.get('support') if 'adv_levels' in dir() else None
            _resistance = adv_levels.get('resistance') if 'adv_levels' in dir() else None
            _atr = atr_info['atr'] if atr_info else None
            _close = df_d1['close'].iloc[-1] if df_d1 is not None and len(df_d1) > 0 else None
            
            # Объединённый вердикт
            _uni = get_unified_verdict(
                signal_type, _short_score, _ofi, _cd,
                _trend_up, _trend_down,
                _support, _resistance, _atr, _close,
                hi2_value=hi2_value
            )
            
            st.markdown("---")
            
            # Основной блок решения
            col_v, col_m = st.columns([3, 2])
            with col_v:
                _ls = _uni.get('long_score', 50)
                _ss = _uni.get('short_score', 50)
                if _uni['decision'] == "LONG":
                    _color = '#00ff00' if _ls >= 80 else '#88ff00' if _ls >= 60 else '#ffff00'
                    st.markdown(f"""<div style='background: {_color}22; border-left: 5px solid {_color}; padding: 15px; border-radius: 8px;'>
                    <h2 style='margin:0; color: {_color};'>🎯 РЕШЕНИЕ: 🟢 ВХОД В ЛОНГ</h2>
                    <p style='margin:5px 0;'>Уверенность: {_uni['confidence']} | Скор: {_ls}/100</p>
                    </div>""", unsafe_allow_html=True)
                elif _uni['decision'] == "SHORT":
                    _color = '#ff0000' if _ss >= 80 else '#ff4444' if _ss >= 60 else '#ff8800'
                    st.markdown(f"""<div style='background: {_color}22; border-left: 5px solid {_color}; padding: 15px; border-radius: 8px;'>
                    <h2 style='margin:0; color: {_color};'>🎯 РЕШЕНИЕ: 🔴 ВХОД В ШОРТ</h2>
                    <p style='margin:5px 0;'>Уверенность: {_uni['confidence']} | Скор: {_ss}/100</p>
                    </div>""", unsafe_allow_html=True)
                else:
                    st.markdown(f"""<div style='background: #88888822; border-left: 5px solid #888888; padding: 15px; border-radius: 8px;'>
                    <h2 style='margin:0; color: #aaaaaa;'>🎯 РЕШЕНИЕ: ⛔ НЕ ВХОДИТЬ</h2>
                    <p style='margin:5px 0;'>Уверенность: {_uni['confidence']} | Скор: {_ls}/100</p>
                    </div>""", unsafe_allow_html=True)
                st.caption(_uni['reason'])
            with col_m:
                cols = st.columns(2)
                _l_delta = f"{_ls-50:+d}" if isinstance(_ls, int) and _ls != 50 else None
                _s_delta = f"{_ss-50:+d}" if isinstance(_ss, int) and _ss != 50 else None
                cols[0].metric("Лонг", f"{_ls}/100" if _ls != '—' else "—", delta=_l_delta)
                cols[1].metric("Шорт", f"{_ss}/100" if _ss != '—' else "—", delta=_s_delta)
            
            # Ключевые метрики
            _trend_line = "📈 Бычий" if _trend_up else ("📉 Медвежий" if _trend_down else "◼ Боковик")
            _hi2_line = f"HI2:{hi2_value:.0f}" if hi2_value else "HI2:—"
            _ofi_line = f"OFI:{_ofi['ofi']:+.2f}" if _ofi else "OFI:—"
            _cd_line = f"CumΔ:{'📈' if _cd and _cd.get('delta_trend')=='растёт' else '📉' if _cd else '—'}"
            st.caption(f"{_trend_line} | {_hi2_line} | {_ofi_line} | {_cd_line}")
            
            # Уровни входа/выхода
            if _uni['decision'] != "WAIT":
                col_e, col_s, col_t = st.columns(3)
                with col_e:
                    st.metric("Вход", f"{_uni['entry_price']:.2f}" if _uni['entry_price'] else "—")
                with col_s:
                    st.metric("Стоп-лосс", f"{_uni['stop_loss']:.2f}" if _uni['stop_loss'] else "—")
                with col_t:
                    st.metric("Цель", f"{_uni['target']:.2f}" if _uni['target'] else "—", 
                             delta=f"+{_uni['potential_pct']:.1f}%" if _uni['potential_pct'] else None)
            else:
                st.caption("📐 Уровни: ждать сигнала для расчёта входа/выхода")
            
            # Калькулятор позиции (всегда показываем, если есть сигнал)
            if _uni['decision'] != "WAIT" and _uni['entry_price'] and _uni['stop_loss']:
                _risk_rub = _deposit * _risk_pct / 100
                _risk_per_contract = abs(_uni['entry_price'] - _uni['stop_loss']) * 10  # лот уточняется
                
                # Уточняем лот для тикера
                _lot = 1000 if selected_ticker in ['CNYRUBF', 'USDRUBF', 'EURRUBF'] else 10
                _risk_per_contract = abs(_uni['entry_price'] - _uni['stop_loss']) * _lot
                
                if _risk_per_contract > 0:
                    _position_size = int(_risk_rub / _risk_per_contract)
                    if _position_size > 0:
                        st.success(f"💰 Калькулятор позиции: **{_position_size}** контрактов (риск {_risk_rub:,.0f} ₽ = {_risk_pct}% от {_deposit:,.0f} ₽)".replace(",", " "))
                    else:
                        st.warning(f"⚠️ Риск {_risk_rub:,.0f} ₽ меньше стоимости 1 контракта. Увеличьте депозит или риск.")
                else:
                    st.info("📐 Стоп-лосс не задан — невозможно рассчитать позицию")
            
            # Кнопка записи в журнал (если есть сигнал LONG или SHORT)
            if _uni['decision'] != "WAIT":
                st.markdown("---")
                col_j, col_b = st.columns([3, 1])
                with col_j:
                    _journal_note = st.text_input("Заметка к сделке (опционально)", key="journal_note", placeholder="Например: по тренду, отбой от поддержки")
                with col_b:
                    if st.button("📝 Записать в журнал", key="journal_btn"):
                        _journal_file = DATA_ROOT / "trade_journal.parquet"
                        _journal_entry = pd.DataFrame([{
                            'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'ticker': selected_ticker,
                            'signal': _uni['decision'],
                            'entry_price': _uni['entry_price'],
                            'stop_loss': _uni['stop_loss'],
                            'target': _uni['target'],
                            'position_size': _position_size if '_position_size' in dir() else 0,
                            'deposit': _deposit,
                            'risk_pct': _risk_pct,
                            'confidence': _uni['confidence'],
                            'reason': _uni['reason'],
                            'note': _journal_note if '_journal_note' in dir() else '',
                        }])
                        
                        if _journal_file.exists():
                            _journal_old = pd.read_parquet(_journal_file)
                            _journal_new = pd.concat([_journal_old, _journal_entry], ignore_index=True)
                        else:
                            _journal_new = _journal_entry
                        
                        _journal_new.to_parquet(_journal_file, index=False)
                        st.success(f"✅ Сделка записана в журнал! (всего записей: {len(_journal_new)})")
                        st.balloons()
            
            # Раскрывающаяся подсказка
            with st.expander("ℹ️ Как принимается решение?"):
                st.markdown(f"""
**Иерархия сигналов:**
- 🔴 **FutOI (40%)** — главный фильтр: {_uni['futoi_contribution']:+.1f}
- 🟡 **TradeStats (30%)** — сила сигнала: {_uni['trade_contribution']:+.1f}
- 🟢 **Order Flow (20%)** — подтверждение: {_uni['ofi_contribution']:+.1f}
- 🔵 **Тренд (10%)** — контекст: {_uni['trend_contribution']:+.1f}
**Итого:** {_uni['total_score']:+.1f} / 100

**Логика:**
- Если вердикт NEUTRAL → не входим, что бы ни показывали остальные
- Если сигнал есть, но OFI/CumDelta противоречат → дивергенция, ждать
- Тренд против сигнала → повышенный риск, уверенность снижается
- Уровни входа/выхода на основе VP + FutOI + HI2
                """)
            
            st.markdown("---")

            # === ПОЯСНЕНИЯ ===            # === ПОЯСНЕНИЯ ===
            with st.expander("ℹ️ Как читать таблицу участников?"):
                st.markdown("""
### Кто такие физики и юрики?
- **Физики (Физ)** — частные трейдеры и мелкие инвесторы. Много участников, маленький капитал у каждого.
- **Юрики (Юр)** — институционалы: банки, фонды, УК. Мало участников, огромные капиталы.
### % покупателей — это про КОЛИЧЕСТВО сделок
`91.2% покупателей` у физиков = из 100 сделок 91 была на покупку.
Но одна сделка юрика может быть в 100 раз крупнее сделки физика.
### Почему оба могут доминировать?
- Физики: 1000 мелких покупок → 90% покупок → доминируют как покупатели.
- Юрики: 5 крупных продаж → 70% продаж → доминируют как продавцы.
- Итог: юрики продают крупно, физики покупают мелко → **Дистрибуция**.
### Дистрибуция vs Аккумуляция
- **Дистрибуция** — юрики продают, физики покупают. Крупные игроки скидывают позицию толпе. Медвежий сигнал.
- **Аккумуляция** — юрики покупают, физики продают. Крупные игроки набирают позицию. Бычий сигнал.
- **Единство** — обе группы покупают или продают. Тренд поддерживается всеми.
### HI2 (концентрация)
- Показывает, насколько позиции сконцентрированы у крупных игроков.
- \> 70 — высокая, \> 150 — очень высокая, \> 500 — экстремальная.
                """)
            # === ЛЕВАЯ И ПРАВАЯ КОЛОНКИ ===
            col_left, col_right = st.columns([3, 2])
            with col_left:
                st.markdown(signal_info)
                # Расчёт дельты за 1 час
                delta_fiz_1h, delta_yur_1h = calculate_delta_1h(df_analytics)
                
                # Основные метрики (3 колонки)
                col1, col2, col3 = st.columns(3)
                fiz_long_pct = latest['pos_long_fiz'] / (latest['pos_long_fiz'] + latest['pos_short_fiz'] + 1) * 100
                yur_short_pct = latest['pos_short_yur'] / (latest['pos_long_yur'] + latest['pos_short_yur'] + 1) * 100
                diff_pct = fiz_long_pct - yur_short_pct
                
                # Стрелка для физиков
                if delta_fiz_1h is not None:
                    fiz_arrow = "▲" if delta_fiz_1h > 0.1 else "▼" if delta_fiz_1h < -0.1 else "▬"
                    fiz_delta_str = f"{delta_fiz_1h:+.1f}% за 1 час"
                else:
                    fiz_arrow = ""
                    fiz_delta_str = "нет данных"
                
                # Стрелка для юриков
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
                    fig_hi2 = go.Figure()
                    fig_hi2.add_trace(go.Scatter(
                        x=hi2_history['tradedate'],
                        y=hi2_history['value'],
                        mode='lines+markers',
                        name='HI2',
                        line=dict(color='#FFA500', width=2),
                        marker=dict(size=4)
                    ))
                    # Зоны
                    fig_hi2.add_hrect(y0=0, y1=40, fillcolor="green", opacity=0.1, line_width=0)
                    fig_hi2.add_hrect(y0=40, y1=70, fillcolor="yellow", opacity=0.1, line_width=0)
                    fig_hi2.add_hrect(y0=70, y1=hi2_history['value'].max() + 10, fillcolor="red", opacity=0.1, line_width=0)
                    fig_hi2.add_hline(y=40, line_dash="dash", line_color="green", opacity=0.5)
                    fig_hi2.add_hline(y=70, line_dash="dash", line_color="red", opacity=0.5)
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
            # === УЛУЧШЕННЫЕ УРОВНИ ПОДДЕРЖКИ/СОПРОТИВЛЕНИЯ ===
            hi2_data = load_hi2_data()
            atr_val = atr_info['atr'] if atr_info else None
            adv_levels = calculate_advanced_levels(df_d1, df_analytics, hi2_data, selected_ticker, atr_val)
            
            with st.expander("📐 Уровни поддержки/сопротивления (VP + FutOI + HI2)", expanded=False):
                if adv_levels['support'] or adv_levels['resistance']:
                    def get_strength(sources):
                        n = len(sources)
                        if n >= 3: return "🟢🟢🟢", "сильный (3/3)", "Высокая надёжность — можно ставить заявки"
                        elif n >= 2: return "🟡🟡⚪", "средний (2/3)", "Можно опираться, но ждать подтверждения"
                        else: return "🔴⚪⚪", "слабый (1/3)", "Ориентир — ждать сигнал от других источников"
                    col_s, col_r = st.columns(2)
                    with col_s:
                        st.markdown("**🛡️ ПОДДЕРЖКА**")
                        if adv_levels['support']:
                            bar, label, desc = get_strength(adv_levels['support_sources'])
                            src = ', '.join(adv_levels['support_sources'])
                            st.metric("Уровень", f"{adv_levels['support']:.2f}", delta=f"{bar} {label}")
                            st.caption(f"📌 Источники: {src}")
                            st.caption(f"📝 {desc}")
                            if df_d1 is not None and len(df_d1) > 0:
                                last_close = df_d1['close'].iloc[-1]
                                dist = (last_close - adv_levels['support']) / adv_levels['support'] * 100
                                if dist < 0: st.caption(f"⚠️ Цена {last_close:.2f} ПРОБИЛА поддержку ({dist:.1f}%) — ослаблен")
                                elif dist < 1: st.caption(f"🔍 Цена {last_close:.2f} у поддержки ({dist:.1f}%) — тест")
                                else: st.caption(f"✅ Цена выше поддержки на {dist:.1f}%")
                        else: st.info("Нет данных")
                    with col_r:
                        st.markdown("**🚀 СОПРОТИВЛЕНИЕ**")
                        if adv_levels['resistance']:
                            bar, label, desc = get_strength(adv_levels['resistance_sources'])
                            src = ', '.join(adv_levels['resistance_sources'])
                            st.metric("Уровень", f"{adv_levels['resistance']:.2f}", delta=f"{bar} {label}")
                            st.caption(f"📌 Источники: {src}")
                            st.caption(f"📝 {desc}")
                            if df_d1 is not None and len(df_d1) > 0:
                                last_close = df_d1['close'].iloc[-1]
                                dist = (adv_levels['resistance'] - last_close) / last_close * 100
                                if dist < 0: st.caption(f"🚀 Цена {last_close:.2f} ПРОБИЛА сопротивление ({abs(dist):.1f}%) — ослаблен")
                                elif dist < 1: st.caption(f"🔍 Цена {last_close:.2f} у сопротивления ({dist:.1f}%) — тест")
                                else: st.caption(f"📈 Сопротивление выше на {dist:.1f}%")
                        else: st.info("Нет данных")
                    st.markdown("---")
                    if adv_levels['poc']:
                        poc = adv_levels['poc']
                        st.caption(f"🎯 **POC:** {poc:.2f} — макс. ликвидность")
                        if df_d1 is not None and len(df_d1) > 0:
                            last_close = df_d1['close'].iloc[-1]
                            poc_dist = (last_close - poc) / poc * 100
                            if last_close > poc: st.caption(f"📈 Цена ВЫШЕ POC на {poc_dist:.1f}% — поддержка")
                            else: st.caption(f"📉 Цена НИЖЕ POC на {abs(poc_dist):.1f}% — сопротивление")
                        if adv_levels['va_high'] and adv_levels['va_low']:
                            st.caption(f"📐 VA диапазон: {adv_levels['va_low']:.2f} — {adv_levels['va_high']:.2f} (ширина {adv_levels['va_high']-adv_levels['va_low']:.2f})")
                    if adv_levels['details']:
                        st.markdown("**🔬 Детали:**")
                        for d in adv_levels['details']: st.caption(f"• {d}")
                    st.markdown("---")
                    st.markdown("**ℹ️ Как пользоваться:** 🟢 Сильный (3/3) — заявки | 🟡 Средний (2/3) — ждать | 🔴 Слабый (1/3) — ориентир")
                else:
                    st.info("Недостаточно данных для расчёта уровней")
            # Обновляем уровни на графике D1 (заменяем high_20/low_20 на новые)
            if adv_levels['support']:
                low_20 = adv_levels['support'] if adv_levels['support'] else low_20
            if adv_levels['resistance']:
                high_20 = adv_levels['resistance'] if adv_levels['resistance'] else high_20
            if adv_levels['poc']:
                poc_price = adv_levels['poc'] if adv_levels['poc'] else poc_price
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
            # === РИСК-МЕНЕДЖМЕНТ (ГО) ===
            if df_d1 is not None and len(df_d1) > 0:
                last_close = df_d1['close'].iloc[-1]
                atr_val = atr_info['atr'] if atr_info else None
                risk = calculate_risk(selected_ticker, last_close, atr=atr_val, deposit=_deposit)
                
                with st.expander("💰 Параметры инструмента (ГО)", expanded=False):
                    col_r1, col_r2 = st.columns(2)
                    with col_r1:
                        st.metric("ГО (1 лот)", f"{risk['go']:,.0f} ₽".replace(",", " "))
                        st.caption(f"Лот: {risk['lot_size']} | Плечо: {risk['leverage']:.1f}x")
                    with col_r2:
                        st.metric("Стоимость контракта", f"{risk['contract_cost']:,.0f} ₽".replace(",", " "))
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
            # === СВОДКА (ДОБАВЛЕНО ИЗ ТОРГОВОГО ДАШБОРДА) ===
            st.markdown("---")
            st.subheader("📊 ДИНАМИКА ЧИСТЫХ ПОЗИЦИЙ (7 дней)")
            df_last = df_analytics.tail(7)
            if len(df_last) >= 2:
                fig_pos = go.Figure()
                fig_pos.add_trace(go.Scatter(x=df_last['datetime'], y=df_last['phys_net'], mode='lines+markers', name='Физики', line=dict(color='#00BFFF', width=2)))
                fig_pos.add_trace(go.Scatter(x=df_last['datetime'], y=df_last['corp_net'], mode='lines+markers', name='Юрики', line=dict(color='#FF6B6B', width=2)))
                fig_pos.add_hline(y=0, line_dash="dash", line_color="gray")
                fig_pos.update_layout(height=300, template='plotly_dark')
                st.plotly_chart(fig_pos, use_container_width=True)
            
            st.markdown("---")
            st.subheader("📋 ИСТОРИЯ СИГНАЛОВ (10 дней)")
            df_daily = df_analytics.resample('D', on='datetime').last().dropna().tail(10).reset_index()
            if len(df_daily) >= 2:
                hist_data = []
                for i in range(len(df_daily)):
                    row = df_daily.iloc[i]
                    strength = 0
                    if i > 0:
                        prev = df_daily.iloc[i-1]
                        if row['phys_net'] > prev['phys_net']: strength += 1
                        elif row['phys_net'] < prev['phys_net']: strength -= 1
                    if row['fiz_buy_ratio'] > 60: strength += 1
                    elif row['fiz_buy_ratio'] < 40: strength -= 1
                    if strength >= 2: signal = "🟢 LONG"
                    elif strength <= -2: signal = "🔴 SHORT"
                    else: signal = "⚪ NEUTRAL"
                    hist_data.append({"Дата": row['datetime'].strftime('%d.%m'), "Сигнал": signal, "Физ %": f"{row['fiz_buy_ratio']:.1f}%", "Юр %": f"{row['yur_buy_ratio']:.1f}%"})
                st.dataframe(pd.DataFrame(hist_data[::-1]), use_container_width=True, hide_index=True)
            st.markdown("---")
            st.subheader("⚠️ ЧТО ДЕЛАТЬ СЕЙЧАС?")
            if signal_type == "LONG":
                if latest['fiz_buy_ratio'] > 80: st.warning("⚠️ Физики перегреты (fiz_buy > 80). Исторически 67% вероятность коррекции (GAZPF/IMOEXF). Лонг с осторожностью.")
                else: st.success("✅ Можно рассматривать лонг.")
            elif signal_type == "SHORT":
                if latest['fiz_buy_ratio'] < 20: st.warning("⚠️ Физики перепроданы. Шорт с осторожностью.")
                else: st.error("🔴 Можно рассматривать шорт.")
            else:
                st.info("⏳ Ждать чёткого сигнала.")

            # === ORDER FLOW IMBALANCE ===
            if df_ts is not None:
                ofi = calculate_ofi(df_ts)
                cd = calculate_cumulative_delta(df_ts)
                
                st.markdown("---")
                st.subheader("📊 Order Flow & Cumulative Delta")
                
                col_ofi1, col_ofi2, col_ofi3 = st.columns(3)
                with col_ofi1:
                    ofi_val = ofi['ofi']
                    emoji = "🟢" if ofi_val > 0.1 else "🔴" if ofi_val < -0.1 else "⚪"
                    st.metric("OFI (дисбаланс)", f"{ofi_val:+.3f}", delta=f"{emoji} {ofi['pressure']}")
                with col_ofi2:
                    delta_emoji = "📈" if cd['delta_trend'] == 'растёт' else "📉"
                    st.metric("Cumulative Delta", f"{cd['cum_delta']:,.0f}".replace(",", " "), delta=f"{delta_emoji} {cd['delta_trend']}")
                with col_ofi3:
                    div_text = "⚠️ Дивергенция!" if cd['divergence'] or ofi['divergence'] else "✅ Нет дивергенции"
                    st.metric("Дивергенция", div_text)
            
            # === ИНДЕКС ВЫПЛАТ ХЕРРИКА (HPI) ===
            if df_d1 is not None:
                _oi_file = DATA_ROOT / "futoi" / f"{selected_ticker}_futoi.parquet"
                _df_oi = None
                if _oi_file.exists():
                    _fut = pd.read_parquet(_oi_file)
                    # Агрегируем ОИ по дням
                    _fut['tradedate'] = pd.to_datetime(_fut['tradedate'])
                    _oi_daily = _fut.groupby('tradedate').last().reset_index()
                    if 'oi_close' not in _oi_daily.columns and 'pos' in _oi_daily.columns:
                        _oi_daily['oi_close'] = _oi_daily['pos'].abs()
                    _df_oi = _oi_daily
                
                _hpi_result = calculate_hpi(df_d1, _df_oi)
                if _hpi_result:
                    st.markdown("---")
                    st.subheader("📊 Индекс выплат Херрика (HPI)")
                    col_h1, col_h2, col_h3 = st.columns(3)
                    with col_h1:
                        _hpi_emoji = "🟢" if _hpi_result['hpi_signal'] == 'LONG' else "🔴" if _hpi_result['hpi_signal'] == 'SHORT' else "⚪"
                        st.metric("HPI", f"{_hpi_result['hpi']:.2f}", delta=f"{_hpi_emoji} {_hpi_result['hpi_signal']}")
                    with col_h2:
                        st.metric("Объём", f"{_hpi_result['volume']:,}".replace(",", " "))
                    with col_h3:
                        _oi_delta = "▲" if _hpi_result['oi_change'] > 0 else "▼" if _hpi_result['oi_change'] < 0 else "—"
                        st.metric("Δ ОИ", f"{_hpi_result['oi_change']:+,}".replace(",", " "))
                    
                    if _hpi_result.get('note'):
                        st.caption(f"ℹ️ {_hpi_result['note']}")
                    if _hpi_result['divergence']:
                        _hpi_val = _hpi_result['hpi']
                        if _hpi_val > 0:
                            _hpi_msg = f"⚠️ Дивергенция HPI: капитал заходит (HPI={_hpi_val:+.1f}), но цена не растёт — возможен скрытый набор позиции."
                        else:
                            _hpi_msg = f"⚠️ Дивергенция HPI: капитал уходит (HPI={_hpi_val:+.1f}), но цена не падает — рост может быть неустойчивым."
                        st.warning(_hpi_msg)

            
elif page == "FUTOI_1H":
    st.title("⏱️ FUTOI 1H — Часовая аналитика")
    df_1h, tickers_1h = load_futoi_1h_data()
    if df_1h is None:
        st.error("Данные FUTOI 1H не найдены")
    else:
        selected_ticker = st.selectbox("Выберите тикер", tickers_1h, key="futoi1h_ticker")
        df_t = df_1h[df_1h["ticker"] == selected_ticker].copy()
        df_t = df_t.sort_values("hour")
        if df_t.empty:
            st.warning(f"Нет данных для {selected_ticker}")
        else:
            latest = df_t.iloc[-1]
            prev = df_t.iloc[-2] if len(df_t) > 1 else latest
            fiz_delta = latest["fiz_ratio_delta"]
            yur_delta = latest["yur_ratio_delta"]
            # === 🎯 ТАКТИЧЕСКОЕ РЕШЕНИЕ (1H) ===
            # Загружаем D1-решение
            _d1_candle = DATA_ROOT / "candles" / f"{selected_ticker}_D1.parquet"
            _d1_df = pd.read_parquet(_d1_candle) if _d1_candle.exists() else None
            _d1_signal = "NEUTRAL"
            _d1_long = 50
            _d1_short = 50
            if _d1_df is not None and len(_d1_df) >= 20:
                if 'sma20' not in _d1_df.columns:
                    _d1_df['sma20'] = _d1_df['close'].rolling(20).mean()
                _d1_last = _d1_df['close'].iloc[-1]
                _d1_sma = _d1_df['sma20'].iloc[-1]
                _d1_trend_up = _d1_last > _d1_sma * 1.02
                _d1_trend_down = _d1_last < _d1_sma * 0.98
                _d1_garch = calculate_garch_for_ticker(_d1_df, selected_ticker) if _d1_df is not None else {}
                _d1_garch_vol = _d1_garch.get('garch_vol', 0)
                
                if latest['fiz_buy_ratio'] > 60: _d1_signal = "LONG"
                elif latest['fiz_buy_ratio'] < 40: _d1_signal = "SHORT"
                if _d1_garch_vol > 30: _d1_signal = "BLOCKED_" + _d1_signal
                
                _d1_long = 85 if _d1_signal == "LONG" else 35 if _d1_signal == "NEUTRAL" else 15
                _d1_short = 15 if _d1_signal == "LONG" else 35 if _d1_signal == "NEUTRAL" else 85
                if "BLOCKED" in _d1_signal: _d1_long = 50; _d1_short = 50
            
            # Тактический сигнал 1H
            _sig_1h = "NEUTRAL"
            if fiz_delta is not None and pd.notna(fiz_delta):
                if latest['fiz_buy_ratio'] > 60 and fiz_delta > 0.1: _sig_1h = "LONG"
                elif latest['fiz_buy_ratio'] < 40 and fiz_delta < -0.1: _sig_1h = "SHORT"
            _agree = (_sig_1h == _d1_signal) or _sig_1h == "NEUTRAL" or _d1_signal == "NEUTRAL"
            
            # Нетто-позиция
            _df_7d = df_t[df_t['hour'] >= df_t['hour'].max() - pd.Timedelta(days=7)]
            _netto_trend = "—"
            _netto_signal = ""
            if len(_df_7d) >= 2:
                _netto_first = _df_7d.iloc[0]
                _netto_last = _df_7d.iloc[-1]
                _phys_net = _netto_last['fiz_long'] - _netto_last['fiz_short']
                _phys_prev = _netto_first['fiz_long'] - _netto_first['fiz_short']
                _netto_trend = "▲ растёт" if _phys_net > _phys_prev else "▼ падает"
                if _phys_net > _phys_prev:
                    _netto_signal = "🟢 Физики набирают лонг"
                else:
                    _netto_signal = "🔴 Физики сокращают лонг"
            
            # Дельта 1H
            _delta_1h = df_t.tail(5)
            _delta_summary = ""
            if len(_delta_1h) >= 3:
                _fiz_d_sum = _delta_1h['fiz_ratio_delta'].sum()
                _yur_d_sum = _delta_1h['yur_ratio_delta'].sum()
                if _fiz_d_sum > 0.2 and _yur_d_sum < -0.2:
                    _delta_summary = "🔴 Дистрибуция (физики покупают, юрики продают)"
                elif _fiz_d_sum < -0.2 and _yur_d_sum > 0.2:
                    _delta_summary = "🟢 Аккумуляция (физики продают, юрики покупают)"
                elif _fiz_d_sum > 0.2 and _yur_d_sum > 0.2:
                    _delta_summary = "🟢 Единство в лонге"
                elif _fiz_d_sum < -0.2 and _yur_d_sum < -0.2:
                    _delta_summary = "🔴 Единство в шорте"
                else:
                    _delta_summary = "⚪ Нейтрально"
            
            # H1-свечи
            _h1_file = DATA_ROOT / "candles" / f"{selected_ticker}_H1.parquet"
            _df_h1 = pd.read_parquet(_h1_file) if _h1_file.exists() else None
            
            # Тренд 1H
            _h1_trend = "◼ Боковик"
            if _df_h1 is not None and len(_df_h1) >= 20:
                if 'sma20' not in _df_h1.columns:
                    _df_h1['sma20'] = _df_h1['close'].rolling(20).mean()
                _h1_last = _df_h1['close'].iloc[-1]
                _h1_sma = _df_h1['sma20'].iloc[-1]
                if _h1_last < _h1_sma * 0.998: _h1_trend = "📉 Медвежий"
                elif _h1_last > _h1_sma * 1.002: _h1_trend = "📈 Бычий"
            
            # Агрессивность
            _agg_1h = calculate_aggression_1h(_df_h1, df_t)
            
            # GARCH 1H
            _garch_1h = calculate_garch_for_ticker(_df_h1, selected_ticker) if _df_h1 is not None else {}
            _garch_1h_vol = _garch_1h.get('garch_vol', 0)
            
            # Итоговый вывод
            _final_decision = "⏳ ЖДАТЬ"
            _final_reason = ""
            if _d1_signal == "LONG" and _sig_1h == "LONG" and _netto_trend == "▲ растёт":
                _final_decision = "✅ ВХОД В ЛОНГ"
                _final_reason = "D1 в лонг, 1H подтверждает, нетто растёт"
            elif _d1_signal == "SHORT" and _sig_1h == "SHORT" and _netto_trend == "▼ падает":
                _final_decision = "✅ ВХОД В ШОРТ"
                _final_reason = "D1 в шорт, 1H подтверждает, нетто падает"
            elif _d1_signal in ("LONG", "SHORT") and _sig_1h == "NEUTRAL":
                _final_decision = "⏳ ЖДАТЬ"
                _final_reason = f"D1 в {_d1_signal}, но 1H нейтрален — ждать тактического сигнала"
            elif _d1_signal == "NEUTRAL":
                _final_decision = "⛔ НЕ ВХОДИТЬ"
                _final_reason = "Стратегический сигнал NEUTRAL"
            else:
                _final_decision = "⚠️ ОСТОРОЖНО"
                _final_reason = "Сигналы противоречивы — проверить все условия"
            
            # === ОТОБРАЖЕНИЕ ===
            st.markdown("---")
            
            # D1 строка
            _d1_emoji = "🟢" if "LONG" in _d1_signal else "🔴" if "SHORT" in _d1_signal else "⚪"
            _garch_d1_str = f" | GARCH: {_d1_garch_vol:.1f}%" if _d1_garch_vol > 0 else ""
            st.caption(f"📌 D1: {_d1_emoji} {_d1_signal} | Лонг: {_d1_long}/100 | Шорт: {_d1_short}/100{_garch_d1_str}")
            
            # Итоговое решение
            if "ВХОД" in _final_decision:
                st.success(f"🎯 {_final_decision}")
            elif "НЕ ВХОДИТЬ" in _final_decision:
                st.error(f"🎯 {_final_decision}")
            else:
                st.info(f"🎯 {_final_decision}")
            st.caption(_final_reason)
            
            # Детали
            _detail = f"Нетто: {_netto_signal} ({_netto_trend})"
            if _delta_summary: _detail += f" | Дельта: {_delta_summary}"
            _detail += f" | Тренд: {_h1_trend}"
            _detail += f" | Агрессивность: {_agg_1h['score']}/100 {_agg_1h['level']}"
            if _garch_1h_vol > 0: _detail += f" | GARCH: {_garch_1h_vol:.1f}%"
            st.caption(_detail)
            
            # Ключевые метрики
            _metr = f"fiz: {latest['fiz_buy_ratio']:.1f}% (Δ{fiz_delta:+.1f}%)" if pd.notna(fiz_delta) else f"fiz: {latest['fiz_buy_ratio']:.1f}%"
            _metr += f" | yur: {latest['yur_buy_ratio']:.1f}%"
            if _df_h1 is not None and len(_df_h1) > 0:
                _metr += f" | Цена: {_df_h1['close'].iloc[-1]:.2f}"
            if _agg_1h['fiz_direction'] != '—':
                _metr += f" | Физ: {_agg_1h['fiz_direction']} ({_agg_1h['fiz_strength']}%)"
            if _agg_1h['yur_direction'] != '—':
                _metr += f" | Юр: {_agg_1h['yur_direction']} ({_agg_1h['yur_strength']}%)"
            st.caption(_metr)
            
            # Предупреждения
            _warnings = []
            if latest['fiz_buy_ratio'] > 80: _warnings.append("Физики перегреты (67% вероятность коррекции)")
            if latest['fiz_buy_ratio'] < 20: _warnings.append("Физики перепроданы")
            if _df_h1 is not None and len(_df_h1) > 0:
                _h1_close = _df_h1['close'].iloc[-1]
                if 'adv_levels_1h' in dir() and adv_levels_1h:
                    if adv_levels_1h.get('support') and _h1_close < adv_levels_1h['support']:
                        _warnings.append(f"Цена пробила поддержку {adv_levels_1h['support']:.2f}")
                    if adv_levels_1h.get('resistance') and _h1_close > adv_levels_1h['resistance']:
                        _warnings.append(f"Цена пробила сопротивление {adv_levels_1h['resistance']:.2f}")
            if not _agree and _sig_1h != "NEUTRAL":
                _warnings.append("1H противоречит D1 — осторожно!")
            if _garch_1h_vol > 25:
                _warnings.append(f"RVI экстремальный ({_garch_1h_vol:.1f}%)")
            if _warnings:
                st.warning("⚠️ " + " | ".join(_warnings))
            
            # Пояснения
            with st.expander("ℹ️ Что значат предупреждения?"):
                st.markdown("""
**Физики перегреты (fiz_buy_ratio > 80%):**
- Больше 80% сделок физиков — на покупку. Слишком агрессивный спрос.
- Когда все купили — некому больше покупать → фиксация прибыли → цена падает.

**Физики перепроданы (fiz_buy_ratio < 40%):**
- Меньше 40% сделок физиков на покупку — активно продают.
- Когда все продали — некому продавливать цену вниз → отскок.

**Пороги:** 60-80% норма, >80% перегреты, <40% перепроданы.

**Цена пробила поддержку/сопротивление:**
- Уровень определён по Volume Profile и FutOI. Пробой = уровень не удержался.
- Возможно дальнейшее движение в сторону пробоя.
                """)
            
            with st.expander("ℹ️ Как читать тактический блок?"):
                st.markdown("""
**D1 (Стратегический сигнал):**
- Главный фильтр. Определяет направление торговли.
- Формируется: FutOI (40%) + TradeStats (30%) + Order Flow (20%) + Тренд (10%).
- Если NEUTRAL → не входим ни при каких условиях.

**Нетто-позиция физиков:**
- Чистая позиция физиков = лонг − шорт.
- ▲ растёт → усиливает D1 LONG / ослабляет D1 SHORT.
- ▼ падает → ослабляет D1 LONG / усиливает D1 SHORT.

**Дельта 1H:**
- Изменение fiz/yur_buy_ratio за последние часы.
- Аккумуляция (физ продают, юр покупают) → бычий сигнал.
- Дистрибуция (физ покупают, юр продают) → медвежий сигнал.

**Тренд (SMA20):**
- 📈 Бычий → поддержка LONG, риск для SHORT.
- 📉 Медвежий → поддержка SHORT, риск для LONG.

**Агрессивность:**
- Показывает, кто активен: физики или юрики.
- Высокая (>60) → сильное движение.

**GARCH (1H):**
- Ожидаемая волатильность. >20% — уменьшить позицию, >25% — экстремально.

**Как принимается итоговое решение:**
- D1 LONG + 1H LONG + нетто ▲ = ✅ ВХОД В ЛОНГ
- D1 SHORT + 1H SHORT + нетто ▼ = ✅ ВХОД В ШОРТ
- D1 NEUTRAL = ⛔ НЕ ВХОДИТЬ
- Противоречия = ⏳ ЖДАТЬ
                """)
            
            st.markdown("---")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("% покупателей среди физиков", f"{latest['fiz_buy_ratio']:.1f}%", delta=f"{fiz_delta:+.1f}%" if pd.notna(fiz_delta) else "—")
            with col2:
                st.metric("% покупателей среди юриков", f"{latest['yur_buy_ratio']:.1f}%", delta=f"{yur_delta:+.1f}%" if pd.notna(yur_delta) else "—")
            with col3:
                st.metric("Позиции (Long/Short)", f"{latest['fiz_long']:,.0f} / {latest['fiz_short']:,.0f}".replace(",", " "))
            col_l, col_r = st.columns([3, 2])
            with col_l:
                st.subheader("Динамика ratio")
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=df_t["hour"], y=df_t["fiz_buy_ratio"], mode="lines", name="Физ (% покупок)", line=dict(color="#00BFFF", width=2)))
                fig.add_trace(go.Scatter(x=df_t["hour"], y=df_t["yur_buy_ratio"], mode="lines", name="Юр (% покупок)", line=dict(color="#FF6B6B", width=2)))
                fig.update_layout(title=f"FUTOI 1H — {selected_ticker}", xaxis_title="Дата", yaxis_title="% покупателей", height=450, template="plotly_dark")
                st.plotly_chart(fig, use_container_width=True)
            with col_r:
                st.subheader("Дельта за 1 час")
                _delta_df = df_t.tail(10)[["hour", "fiz_ratio_delta", "yur_ratio_delta"]].copy()
                _delta_lines = []
                for _, row in _delta_df.iterrows():
                    fiz_d = row['fiz_ratio_delta']
                    yur_d = row['yur_ratio_delta']
                    f_arrow = "▲" if fiz_d > 0 else "▼" if fiz_d < 0 else "▬"
                    y_arrow = "▲" if yur_d > 0 else "▼" if yur_d < 0 else "▬"
                    
                    if fiz_d > 0.05 and yur_d < -0.05:
                        _action = "Физики покупают, юрики продают"
                    elif fiz_d < -0.05 and yur_d > 0.05:
                        _action = "Физики продают, юрики покупают"
                    elif fiz_d > 0.05 and yur_d > 0.05:
                        _action = "Обе группы покупают"
                    elif fiz_d < -0.05 and yur_d < -0.05:
                        _action = "Обе группы продают"
                    else:
                        _action = "Нейтрально"
                    
                    _t = pd.to_datetime(row['hour']).strftime("%H:%M")
                    _delta_lines.append(f"{_t} Физ:{f_arrow}{abs(fiz_d):.1f}% Юр:{y_arrow}{abs(yur_d):.1f}% → {_action}")
                
                _delta_text = "\n".join(_delta_lines)
                st.text(_delta_text)
            with st.expander("📋 Последние записи (15)", expanded=False):
                st.subheader("Последние записи")
                st.dataframe(df_t.tail(15)[["hour", "fiz_buy_ratio", "yur_buy_ratio", "fiz_ratio_delta", "yur_ratio_delta"]].rename(columns={"fiz_buy_ratio": "Физ %", "yur_buy_ratio": "Юр %", "fiz_ratio_delta": "Физ Δ", "yur_ratio_delta": "Юр Δ"}), use_container_width=True, hide_index=True)
            # === УРОВНИ ПОДДЕРЖКИ/СОПРОТИВЛЕНИЯ (1H) ===
            h1_file = DATA_ROOT / "candles" / f"{selected_ticker}_H1.parquet"
            df_h1 = pd.read_parquet(h1_file) if h1_file.exists() else None
            adv_levels_1h = calculate_advanced_levels_1h(df_h1, df_t, selected_ticker)
            
            with st.expander("📐 Уровни поддержки/сопротивления (VP + FutOI)", expanded=True):
                if adv_levels_1h['support'] or adv_levels_1h['resistance']:
                    def get_strength_1h(sources):
                        n = len(sources)
                        if n >= 2: return "🟡🟡", "сильный (2/2)", "Оба источника совпадают — высокая надёжность"
                        else: return "🔴⚪", "слабый (1/2)", "Один источник — ориентир, ждать подтверждения"
                    col_s, col_r = st.columns(2)
                    with col_s:
                        st.markdown("**🛡️ ПОДДЕРЖКА**")
                        if adv_levels_1h['support']:
                            bar, label, desc = get_strength_1h(adv_levels_1h['support_sources'])
                            src = ', '.join(adv_levels_1h['support_sources'])
                            st.metric("Уровень", f"{adv_levels_1h['support']:.2f}", delta=f"{bar} {label}")
                            st.caption(f"📌 Источники: {src}")
                            st.caption(f"📝 {desc}")
                            if df_h1 is not None and len(df_h1) > 0:
                                last_close = df_h1['close'].iloc[-1]
                                dist = (last_close - adv_levels_1h['support']) / adv_levels_1h['support'] * 100
                                if dist < 0: st.caption(f"⚠️ Цена {last_close:.2f} ПРОБИЛА поддержку ({dist:.1f}%) — ослаблен")
                                elif dist < 1: st.caption(f"🔍 Цена {last_close:.2f} у поддержки ({dist:.1f}%) — тест")
                                else: st.caption(f"✅ Цена выше поддержки на {dist:.1f}%")
                        else: st.info("Нет данных")
                    with col_r:
                        st.markdown("**🚀 СОПРОТИВЛЕНИЕ**")
                        if adv_levels_1h['resistance']:
                            bar, label, desc = get_strength_1h(adv_levels_1h['resistance_sources'])
                            src = ', '.join(adv_levels_1h['resistance_sources'])
                            st.metric("Уровень", f"{adv_levels_1h['resistance']:.2f}", delta=f"{bar} {label}")
                            st.caption(f"📌 Источники: {src}")
                            st.caption(f"📝 {desc}")
                            if df_h1 is not None and len(df_h1) > 0:
                                last_close = df_h1['close'].iloc[-1]
                                dist = (adv_levels_1h['resistance'] - last_close) / last_close * 100
                                if dist < 0: st.caption(f"🚀 Цена {last_close:.2f} ПРОБИЛА сопротивление ({abs(dist):.1f}%) — ослаблен")
                                elif dist < 1: st.caption(f"🔍 Цена {last_close:.2f} у сопротивления ({dist:.1f}%) — тест")
                                else: st.caption(f"📈 Сопротивление выше на {dist:.1f}%")
                        else: st.info("Нет данных")
                    st.markdown("---")
                    if adv_levels_1h['poc']:
                        poc = adv_levels_1h['poc']
                        st.caption(f"🎯 **POC:** {poc:.2f} — макс. ликвидность")
                        if df_h1 is not None and len(df_h1) > 0:
                            last_close = df_h1['close'].iloc[-1]
                            poc_dist = (last_close - poc) / poc * 100
                            if last_close > poc: st.caption(f"📈 Цена ВЫШЕ POC на {poc_dist:.1f}% — поддержка")
                            else: st.caption(f"📉 Цена НИЖЕ POC на {abs(poc_dist):.1f}% — сопротивление")
                        if adv_levels_1h['va_high'] and adv_levels_1h['va_low']:
                            st.caption(f"📐 VA диапазон: {adv_levels_1h['va_low']:.2f} — {adv_levels_1h['va_high']:.2f} (ширина {adv_levels_1h['va_high']-adv_levels_1h['va_low']:.2f})")
                    if adv_levels_1h['details']:
                        st.markdown("**🔬 Детали:**")
                        for d in adv_levels_1h['details']: st.caption(f"• {d}")
                    st.markdown("---")
                    st.markdown("**ℹ️ Как пользоваться:** 🟡 Сильный (2/2) — заявки | 🔴 Слабый (1/2) — ориентир")
                else:
                    st.info("Недостаточно данных для расчёта уровней")
            st.markdown("---")

            _h1_file_rm = DATA_ROOT / "candles" / f"{selected_ticker}_H1.parquet"
            _df_h1_rm = pd.read_parquet(_h1_file_rm) if _h1_file_rm.exists() else None
            _last_close_rm = _df_h1_rm["close"].iloc[-1] if _df_h1_rm is not None and len(_df_h1_rm) > 0 else 0
            _atr_rm = (_df_h1_rm["high"] - _df_h1_rm["low"]).tail(14).mean() if _df_h1_rm is not None and len(_df_h1_rm) > 14 else None
            risk_1h = calculate_risk(selected_ticker, _last_close_rm, atr=_atr_rm)
            with st.expander("💰 Риск-менеджмент (ГО и позиция)", expanded=False):
                col_r1, col_r2, col_r3 = st.columns(3)
                with col_r1:
                    st.metric("ГО (1 лот)", f"{risk_1h['go']:,.0f} ₽".replace(",", " "))
                    st.caption(f"Лот: {risk_1h['lot_size']}")
                with col_r2:
                    st.metric("Макс. лотов", f"{risk_1h['max_lots']}", delta=f"Депозит {risk_1h['deposit']:,.0f} ₽".replace(",", " "))
                    st.caption(f"Плечо: {risk_1h['leverage']:.1f}x")
                with col_r3:
                    st.metric("Риск на лот (ATR)", f"{risk_1h['risk_per_lot']:,.0f} ₽".replace(",", " "))
                    st.caption(f"Стоимость контракта: {risk_1h['contract_cost']:,.0f} ₽".replace(",", " "))
            st.subheader("⚠️ ЧТО ДЕЛАТЬ СЕЙЧАС?")
            fiz_ratio = latest['fiz_buy_ratio']
            fiz_delta_val = fiz_delta if pd.notna(fiz_delta) else 0
            if fiz_ratio > 60 and fiz_delta_val > 0:
                st.success("✅ Физики активно покупают. Возможен лонг.")
            elif fiz_ratio < 40 and fiz_delta_val < 0:
                st.error("🔴 Физики активно продают. Возможен шорт.")
            elif fiz_ratio > 80:
                st.warning("⚠️ Физики перегреты (81.5%). Риск разворота ВНИЗ — возможен шорт.")
            elif fiz_ratio < 20:
                st.warning("⚠️ Физики перепроданы. Риск отскока.")
            else:
                st.info("⏳ Нет явного сигнала. Ждать.")
            

elif page == "📊 Сканер фьючерсов":
    st.title("📊 Сканер фьючерсов")
    st.caption("Объединённый анализ: 1D (стратегия) + 4H (тактика) + 1H (точка входа)")
    # === ДОБАВЛЕНИЕ НОВОГО ТИКЕРА ===
    with st.expander("➕ Добавить тикер (вечные, срочные фьючерсы, индексы)", expanded=False):
        # Счётчик для сброса поля ввода
        if 'ticker_input_counter' not in st.session_state:
            st.session_state['ticker_input_counter'] = 0
        if 'add_ticker_error' in st.session_state:
            st.warning(st.session_state['add_ticker_error'])
            if st.button('✕ Скрыть', key='hide_error'):
                del st.session_state['add_ticker_error']
                st.rerun()
        col_type, col_ticker = st.columns([1, 2])
        with col_type:
            _asset_type = st.selectbox("Тип актива", ["Вечный фьючерс", "Срочный фьючерс", "Индекс"], key="scan_type")
        with col_ticker:
            _input_key = f"scan_ticker_{st.session_state['ticker_input_counter']}"
            if _asset_type == "Срочный фьючерс":
                _new_ticker = st.text_input("Короткий код (SI, PT, VI, BR...)", placeholder="Например: SI", key=_input_key).upper().strip()
            else:
                _new_ticker = st.text_input("Тикер", placeholder="Например: NVTKF", key=_input_key).upper().strip()
        
        if 'add_ticker_status' in st.session_state:
            st.toast('✅ Тикер добавлен!', icon='✅')
            with st.expander('📊 Статус добавления', expanded=False):
                st.markdown(st.session_state['add_ticker_status'])
            if st.button('✕ Скрыть', key='hide_status'):
                del st.session_state['add_ticker_status']
                st.rerun()
        def _find_active_contract(sectype_code):
            """Автоопределение актуального полного кода фьючерса через MOEX API.
            Ищет по SECTYPE (короткий код базового актива: SV, BR, SI...).
            Учитывает регистр (Si -> SI)."""
            import requests
            from datetime import datetime
            try:
                _url = 'https://iss.moex.com/iss/engines/futures/markets/forts/securities.json'
                _resp = requests.get(_url, timeout=10)
                if _resp.status_code != 200:
                    return sectype_code
                _data = _resp.json()['securities']
                _cols = _data['columns']
                _rows = _data['data']
                _secid_idx = _cols.index('SECID')
                _sectype_idx = _cols.index('SECTYPE')
                
                _found = []
                for _row in _rows:
                    # Сравниваем без учёта регистра (Si == SI)
                    if _row[_sectype_idx].upper() == sectype_code.upper():
                        _found.append(_row[_secid_idx])
                
                if _found:
                    # Сортируем по дате экспирации, берём ближайший активный
                    _today = datetime.now().strftime('%Y-%m-%d')
                    _lastdate_idx = _cols.index('LASTTRADEDATE') if 'LASTTRADEDATE' in _cols else None
                    if _lastdate_idx is not None:
                        # Фильтруем: дата > сегодня (активные контракты)
                        _active_contracts = []
                        for _row in _rows:
                            if _row[_sectype_idx].upper() == sectype_code.upper():
                                if _row[_lastdate_idx] > _today:
                                    _active_contracts.append((_row[_lastdate_idx], _row[_secid_idx]))
                        if _active_contracts:
                            _active_contracts.sort()
                            return _active_contracts[0][1]
                    return _found[0]
            except:
                pass
            return sectype_code  # fallback
        
        if st.button("✅ Добавить в сканер", key="scan_add_btn"):
            if _new_ticker:
                try:
                    from pathlib import Path
                    import subprocess, os, requests
                    from datetime import datetime, timedelta
                    
                    _board = "RFUD" if _asset_type != "Индекс" else "INDEX"
                    _short_to_full = {
                        'SI': 'SI', 'PT': 'PLT', 'VI': 'RVI', 'BR': 'BR', 'GD': 'GOLD',
                        'RI': 'RTS', 'MX': 'MIX', 'ED': 'ED',
                        'SV': 'SILV', 'PD': 'PLD', 'CL': 'CL', 'NG': 'NG',
                        'CE': 'COPPER', 'AN': 'ALUM', 'ZC': 'ZINC', 'W4': 'WHEAT',
                        'Eu': 'Eu', 'CR': 'CNY', 'TY': 'TRY',
                        'MM': 'MXI', 'OG': 'OGI', 'MA': 'MMI', 'FN': 'FNI',
                    }
                    
                    # ===== ВАЛИДАЦИЯ ТИКЕРА =====
                    _errors = []
                    
                    # Проверка на пробелы и спецсимволы
                    if _new_ticker != _new_ticker.strip():
                        _errors.append('❌ Тикер содержит пробелы в начале или конце')
                    if not _new_ticker.replace('_', '').replace('-', '').isalnum():
                        _errors.append('❌ Тикер содержит недопустимые символы (только A-Z, 0-9, _, -)')
                    if len(_new_ticker) < 1 or len(_new_ticker) > 20:
                        _errors.append('❌ Длина тикера должна быть от 1 до 20 символов')
                    
                    # Для срочных фьючерсов — _short_to_full как справочник, но не жёсткое ограничение
                    # Если тикера нет в справочнике, используем его как есть (может работать)
                    
                    # Проверка, что тикер не дублируется
                    _existing_tickers = set()
                    _futoi_path = DATA_ROOT / 'futoi'
                    if _futoi_path.exists():
                        for _pf in _futoi_path.glob('*_futoi.parquet'):
                            _existing_tickers.add(_pf.stem.replace('_futoi', ''))
                    if _new_ticker in _existing_tickers:
                        _errors.append(f'⚠️ Тикер {_new_ticker} уже существует в системе')
                    
                    if _errors:
                        st.session_state['add_ticker_error'] = '\n'.join(_errors)
                        st.session_state['ticker_input_counter'] += 1
                        st.rerun()
                    
                    # Проверка через MOEX API — существует ли тикер
                    # Автоопределение полного кода
                    if _asset_type == 'Срочный фьючерс':
                        with st.spinner(f'🔍 Ищем актуальный контракт для {_new_ticker}...'):
                            # Ищем по короткому коду (ключ), не по значению из справочника
                            _found = _find_active_contract(_new_ticker)
                            if _found and _found != _new_ticker:
                                _short_to_full[_new_ticker] = _found
                                st.toast(f'✅ Найден: {_new_ticker} → {_found}', icon='🔍')
                    _candle_ticker = _short_to_full.get(_new_ticker, _new_ticker)
                    _full_code = _short_to_full.get(_new_ticker, _new_ticker)
                    
                    # Индексы пока не поддерживаются для FutOI
                    if _board == "INDEX":
                        st.warning(f'⚠️ Индексы пока не поддерживают FutOI. Добавляем только свечи.')
                        _skip_futoi = True
                    else:
                        _skip_futoi = False
                    
                    _test_url = f"https://iss.moex.com/iss/engines/futures/markets/forts/securities/{_candle_ticker}/candles.json"
                    if _board == "INDEX":
                        _test_url = f"https://iss.moex.com/iss/engines/stock/markets/index/securities/{_new_ticker}/candles.json"
                    try:
                        # Проверяем за 5 дней (с запасом на выходные)
                        _test_resp = requests.get(_test_url, params={'from': (datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d'), 'till': datetime.now().strftime('%Y-%m-%d'), 'interval': 24}, timeout=10)
                        if _test_resp.status_code != 200 or 'candles' not in _test_resp.json():
                            st.session_state['add_ticker_error'] = f'❌ Тикер {_new_ticker} не найден на MOEX. Проверьте правильность кода.'
                            st.session_state['ticker_input_counter'] += 1
                            st.rerun()
                        _data_test = _test_resp.json()['candles']
                        if not _data_test.get('data'):
                            st.session_state['add_ticker_error'] = f'❌ Тикер {_new_ticker} найден, но нет свечных данных за последние 5 дней (возможно, выходной).'
                            st.session_state['ticker_input_counter'] += 1
                            st.rerun()
                    except Exception as e:
                        st.session_state['add_ticker_error'] = f'⚠️ Не удалось проверить тикер {_new_ticker}: {str(e)[:100]}'
                        st.session_state['ticker_input_counter'] += 1
                        st.rerun()
                    # ===== КОНЕЦ ВАЛИДАЦИИ =====
                    
                    
                    _status = {}
                    
                    # 1. Свечи D1, H1
                    _h1_df = None
                    for _tf, _interval in [("D1", 24), ("H1", 60)]:
                        try:
                            _url = f"https://iss.moex.com/iss/engines/futures/markets/forts/securities/{_candle_ticker}/candles.json"
                            if _board == "INDEX":
                                _url = f"https://iss.moex.com/iss/engines/stock/markets/index/securities/{_new_ticker}/candles.json"
                            _resp = requests.get(_url, params={'from': (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d'), 'till': datetime.now().strftime('%Y-%m-%d'), 'interval': _interval}, timeout=30)
                            if _resp.status_code == 200 and 'candles' in _resp.json():
                                _data = _resp.json()['candles']
                                if _data['data']:
                                    _df_new = pd.DataFrame(_data['data'], columns=_data['columns'])
                                    _df_new.to_parquet(DATA_ROOT / "candles" / f"{_new_ticker}_{_tf}.parquet", index=False)
                                    if _tf == "H1":
                                        _h1_df = _df_new
                                    _status[f'Свечи {_tf}'] = '✅'
                                else:
                                    _status[f'Свечи {_tf}'] = '⚠️ пусто'
                            else:
                                _status[f'Свечи {_tf}'] = f'❌ HTTP {_resp.status_code}'
                        except Exception as e:
                            _status[f'Свечи {_tf}'] = f'❌ {str(e)[:50]}'
                    
                    # 2. H4 из H1
                    if _h1_df is not None and len(_h1_df) > 0:
                        try:
                            _h1_df['begin'] = pd.to_datetime(_h1_df['begin'])
                            _h1_df['h4_block'] = _h1_df['begin'].dt.floor('4h')
                            _h4 = _h1_df.groupby('h4_block').agg(
                                open=('open','first'), high=('high','max'),
                                low=('low','min'), close=('close','last'), volume=('volume','sum')
                            ).reset_index().rename(columns={'h4_block': 'begin'})
                            _h4.to_parquet(DATA_ROOT / "candles" / f"{_new_ticker}_H4.parquet", index=False)
                            _status['Свечи H4'] = '✅'
                        except Exception as e:
                            _status['Свечи H4'] = f'❌ {str(e)[:50]}'
                    else:
                        _status['Свечи H4'] = '⚠️ нет H1 для агрегации'
                    
                    _futoi_failed = False
                    # 4. Запускаем сборщик FutOI
                    env = os.environ.copy()
                    env['PYTHONPATH'] = '/root/finlab/FinLabPy'
                    try:
                        result = subprocess.run(
                            ['/root/finlab/venv/bin/python', '-c', f'''
import sys; sys.path.insert(0, "/root/finlab/FinLabPy")
from DataCollectors.futoi_collector import collect_futoi, merge_with_existing, DATA_DIR
from MOEXPy.MOEXPy import MOEXPy
from datetime import datetime
import os
api = MOEXPy(token=os.getenv("MOEX_TOKEN"))
df = collect_futoi("{_new_ticker}", api)
if len(df) > 0:
    fp = DATA_DIR / "{_new_ticker}_futoi.parquet"
    merge_with_existing(df, fp).write_parquet(fp)
    print(f"OK: {{len(df)}}")
else:
    print("EMPTY")
'''],
                            env=env, capture_output=True, text=True, timeout=120
                        )
                        # Проверяем, создался ли файл с данными
                        _futoi_file = DATA_ROOT / 'futoi' / f'{_new_ticker}_futoi.parquet'
                        if _futoi_file.exists():
                            _futoi_df = pd.read_parquet(_futoi_file)
                            if len(_futoi_df) > 0:
                                _status['FutOI сбор'] = f'✅ ({len(_futoi_df)} записей)'
                            else:
                                _status['FutOI сбор'] = '❌ нет данных FutOI (актив не поддерживается MOEX)'
                                _futoi_failed = True
                        else:
                            _status['FutOI сбор'] = '❌ нет данных FutOI (файл не создан)'
                            _futoi_failed = True
                    except Exception as e:
                        _status['FutOI сбор'] = f'❌ {str(e)[:50]}'
                    
                    # Если FutOI пустой — блокируем добавление
                    if _futoi_failed:
                        _status['⚠️ ИТОГ'] = '❌ Актив не добавлен: нет данных FutOI. Попробуйте другой тикер.'
                        with st.expander('📊 Статус добавления', expanded=True):
                            for k, v in _status.items():
                                st.caption(f'{k}: {v}')
                            if st.button('🔄 Сбросить и вернуться', key='reset_futoi_fail'):
                                st.session_state.pop('add_ticker_error', None)
                                st.session_state['ticker_input_counter'] = st.session_state.get('ticker_input_counter', 0) + 1
                                st.rerun()
                        st.stop()

                    # 3. Обновляем тикеры во всех сборщиках (только после успешного сбора!)
                    # Сначала обновляем единый конфиг
                    _config_path = Path('/root/finlab/FinLabPy/DataCollectors/tickers_config.json')
                    if _config_path.exists():
                        import json
                        with open(_config_path) as f:
                            _tcfg = json.load(f)
                        if _asset_type == 'Срочный фьючерс' or _asset_type == 'Вечный фьючерс':
                            if _new_ticker not in _tcfg.get('futures', []):
                                _tcfg['futures'].append(_new_ticker)
                        else:
                            if _new_ticker not in _tcfg.get('stocks', []):
                                _tcfg['stocks'].append(_new_ticker)
                        with open(_config_path, 'w') as f:
                            json.dump(_tcfg, f, indent=2, ensure_ascii=False)
                        _status['tickers_config.json'] = '✅ обновлён'

                    _base = Path('/root/finlab/FinLabPy/DataCollectors')
                    _collectors = {
                        _base / 'futoi_1h_aggregator.py': _new_ticker,
                        _base / 'futoi_4h_aggregator.py': _new_ticker,
                        _base / 'futoi_daily_aggregator.py': _new_ticker,
                        _base / 'hi2_collector.py': _full_code,
                        _base / 'candles_collector.py': _full_code if _asset_type == 'Срочный фьючерс' else _new_ticker,
                    }
                    if not _skip_futoi:
                        _collectors[_base / 'futoi_collector.py'] = _full_code if _asset_type == 'Срочный фьючерс' else _new_ticker
                    for _conf_path, _code in _collectors.items():
                        if _conf_path.exists():
                            try:
                                with open(_conf_path) as f:
                                    _txt = f.read()
                                _code_in = _code in _txt
                                if not _code_in:
                                    _txt = _txt.replace("TICKERS = [", f"TICKERS = ['{_code}', ")
                                    with open(_conf_path, 'w') as f:
                                        f.write(_txt)
                                _status[_conf_path.name] = '✅ уже в конфиге' if _code_in else '✅ добавлен в конфиг'
                            except Exception as e:
                                _status[_conf_path.name] = f'❌ {str(e)[:50]}'

                    # 5. Запускаем сборщик HI2 (если не индекс)
                    if not _skip_futoi:
                        try:
                            _hi2_result = subprocess.run(
                                ['/root/finlab/venv/bin/python', '/root/finlab/FinLabPy/DataCollectors/hi2_collector.py'],
                                env=env, capture_output=True, text=True, timeout=120
                            )
                            _hi2_file = DATA_ROOT / 'hi2' / f'{_full_code}_hi2.parquet'
                            if _hi2_file.exists():
                                _status['HI2 данные'] = '✅'
                            else:
                                _status['HI2 данные'] = '⏳ ждёт cron (раз в сутки)'
                        except Exception as e:
                            _status['HI2 данные'] = f'❌ {str(e)[:50]}'
                    else:
                        _status['HI2 данные'] = '⏭️ пропущен (индекс)'

                    # 5.5. Запускаем сборщик свечей
                    try:
                        _candles_result = subprocess.run(
                            ['/root/finlab/venv/bin/python', '/root/finlab/FinLabPy/DataCollectors/candles_collector.py'],
                            env=env, capture_output=True, text=True, timeout=120
                        )
                        _d1_file = DATA_ROOT / 'candles' / f'{_new_ticker}_D1.parquet'
                        if _d1_file.exists():
                            _status['Свечи D1'] = '✅'
                        else:
                            _status['Свечи D1'] = '⏳ ждёт cron (каждый час)'
                    except Exception as e:
                        _status['Свечи D1'] = f'❌ {str(e)[:50]}'

                    # 6. Запускаем сборщик TradeStats
                    if not _skip_futoi:
                        try:
                            _ts_result = subprocess.run(
                                ['/root/finlab/venv/bin/python', '-c', f'''
import sys; sys.path.insert(0, "/root/finlab/FinLabPy")
from DataCollectors.tradestats_collector import collect_tradestats, get_active_code
_code = get_active_code("{_new_ticker}") if "{_new_ticker}" not in ["CNYRUBF","EURRUBF","GAZPF","GLDRUBF","IMOEXF","SBERF","USDRUBF"] else "{_new_ticker}"
collect_tradestats(_code, "RFUD")
'''],
                                env=env, capture_output=True, text=True, timeout=120
                            )
                            _ts_file = DATA_ROOT / 'tradestats' / f'{_new_ticker}_tradestats.parquet'
                            if not _ts_file.exists():
                                _active = _find_active_contract(_new_ticker)
                                _ts_file = DATA_ROOT / 'tradestats' / f'{_active}_tradestats.parquet'
                            _status['TradeStats'] = '✅' if _ts_file.exists() else '⏳ ждёт cron (раз в сутки)'
                        except Exception as e:
                            _status['TradeStats'] = f'❌ {str(e)[:50]}'
                    else:
                        _status['TradeStats'] = '⏭️ пропущен (индекс)'

                    # 6. Итоговая проверка
                    _status['FutOI файл'] = '✅' if (DATA_ROOT / 'futoi' / f'{_new_ticker}_futoi.parquet').exists() else '⏳ ждёт cron'
                    
                    # ====== Уведомление ======
                    _lines = [f'### 📊 Статус добавления: **{_new_ticker}**']
                    for _step, _icon in _status.items():
                        _lines.append(f'{_icon} {_step}')
                    
                    _warnings = [s for s in _status.values() if '❌' in s or '⚠️' in s]
                    if _warnings:
                        _lines.append(f'\n⚠️ **Обнаружено проблем: {len(_warnings)}.** Проверьте логи.')
                    
                    st.session_state['add_ticker_status'] = '\n'.join(_lines)
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f'❌ Критическая ошибка: {e}')
    
    st.markdown("---")

    
    # Автообновление полных кодов для существующих тикеров (раз в сессию)
    if 'codes_updated' not in st.session_state:
        _short_to_full = {
            'SI': 'SI', 'PT': 'PLT', 'VI': 'RVI', 'BR': 'BR', 'GD': 'GOLD',
            'RI': 'RTS', 'MX': 'MIX', 'ED': 'ED',
            'SV': 'SV', 'W4': 'WHEAT', 'Eu': 'Eu', 'CR': 'CNY',
            'SA': 'SUGR', 'AN': 'ALUM', 'PD': 'PLD', 'NG': 'NG',
            'MM': 'MXI', 'OG': 'OGI', 'MA': 'MMI', 'FN': 'FNI',
        }
        _updated_codes = {}
        _failed_codes = []
        for _t in _short_to_full:
            try:
                _sectype = _short_to_full[_t]
                _found = _find_active_contract(_sectype) if _t != _sectype else _find_active_contract(_t)
                if _found and _found != _t:
                    _updated_codes[_t] = _found
                elif not _found or _found == _t:
                    _failed_codes.append(_t)
            except Exception as _e:
                _failed_codes.append(f"{_t}: {str(_e)[:50]}")
        st.session_state['codes_updated'] = True
        st.session_state['active_codes'] = _updated_codes
        if _failed_codes:
            st.session_state['codes_update_errors'] = _failed_codes
        if _updated_codes and st.session_state.get('page_refreshed'):
            st.toast(f'🔄 Коды обновлены: {len(_updated_codes)} тикеров', icon='✅')
            st.session_state['page_refreshed'] = False
        if _updated_codes and st.session_state.get('page_refreshed'):
            st.toast(f'🔄 Коды обновлены: {len(_updated_codes)} тикеров', icon='✅')
            st.session_state['page_refreshed'] = False
    
    if 'codes_update_errors' in st.session_state and st.session_state['codes_update_errors']:
        with st.expander(f'⚠️ Ошибки обновления кодов ({len(st.session_state["codes_update_errors"])} тикеров)', expanded=False):
            for _err in st.session_state['codes_update_errors']:
                st.caption(f'• {_err}')
        if st.button('✕ Скрыть', key='hide_code_errors'):
            del st.session_state['codes_update_errors']
            st.rerun()

    all_data, tickers = load_futoi_data()
    if all_data is None:
        st.error("Данные FutOI не найдены")
    else:
        selected_ticker = st.selectbox("Выберите тикер", tickers, key="scanner_ticker")
        
        # Загружаем данные по трём ТФ
        df_analytics = prepare_futoi_analytics(all_data[all_data['ticker'] == selected_ticker])
        
        # 4H данные
        df_4h = None
        h4_file = DATA_ROOT / "futoi_4h" / "futoi_4h.parquet"
        if h4_file.exists():
            df_4h_all = pd.read_parquet(h4_file)
            df_4h = df_4h_all[df_4h_all['ticker'] == selected_ticker].sort_values('hour')
        
        # 1H данные
        df_1h = None
        h1_file = DATA_ROOT / "futoi_1h" / "futoi_1h.parquet"
        if h1_file.exists():
            df_1h_all = pd.read_parquet(h1_file)
            df_1h = df_1h_all[df_1h_all['ticker'] == selected_ticker].sort_values('hour')
        
        # D1 тренд
        d1_file = DATA_ROOT / "candles" / f"{selected_ticker}_D1.parquet"
        _trend_up = False
        _trend_down = False
        if d1_file.exists():
            _d1_df = pd.read_parquet(d1_file)
            if len(_d1_df) >= 20:
                _d1_df['sma20'] = _d1_df['close'].rolling(20).mean()
                _last = _d1_df['close'].iloc[-1]
                _sma = _d1_df['sma20'].iloc[-1]
                if _last > _sma * 1.02: _trend_up = True
                elif _last < _sma * 0.98: _trend_down = True
        
        # Объединённый вердикт
        # Получаем HI2 и GARCH для вердикта
        _hi2_val = None
        _garch_vol = 0
        _hi2_data = load_hi2_data()
        if _hi2_data is not None:
            _hi2_lookup = selected_ticker
            if selected_ticker == 'BR': _hi2_lookup = 'BRN6'
            _hi2_t = _hi2_data[_hi2_data['ticker'] == _hi2_lookup]
            if len(_hi2_t) > 0:
                _hi2_agr = _hi2_t[_hi2_t['metric'] == 'hhi_agressive']
                if len(_hi2_agr) > 0:
                    _hi2_val = _hi2_agr.sort_values('tradedate').iloc[-1]['value']
        
        _d1_f = DATA_ROOT / "candles" / f"{selected_ticker}_D1.parquet"
        if _d1_f.exists():
            _d1_df = pd.read_parquet(_d1_f)
            if len(_d1_df) >= 20:
                _gr = calculate_garch_for_ticker(_d1_df, selected_ticker)
                _garch_vol = _gr.get('garch_vol', 0)
        
        _is_dist = df_analytics['phys_net'].iloc[-1] > 0 and df_analytics['corp_net'].iloc[-1] < 0 if df_analytics is not None and len(df_analytics) > 0 else False
        _is_accum = df_analytics['phys_net'].iloc[-1] < 0 and df_analytics['corp_net'].iloc[-1] > 0 if df_analytics is not None and len(df_analytics) > 0 else False
        
        # HPI для вердикта
        _hpi_result = None
        _d1_file_hpi = DATA_ROOT / "candles" / f"{selected_ticker}_D1.parquet"
        if _d1_file_hpi.exists():
            _d1_df_hpi = pd.read_parquet(_d1_file_hpi)
            _hpi_result = calculate_hpi(_d1_df_hpi)
        
        # Zweig Filter
        _session_scan = get_session_status()
        _zweig_scan = get_zweig_signal(None, None, _session_scan, _garch_vol)
        _rvi_val2 = None
        try:
            _rvi_file = DATA_ROOT / "sector_indices" / "RVI_D1.parquet"
            if not _rvi_file.exists():
                _rvi_file = DATA_ROOT / "sector_indices" / "RVI_D1.parquet"
            if _rvi_file.exists():
                _rvi_df = pd.read_parquet(_rvi_file)
                if len(_rvi_df) > 0:
                    _rvi_val2 = _rvi_df["close"].iloc[-1]
        except:
            pass
        
        scanner = get_unified_scanner_verdict(
            df_analytics, df_4h, df_1h, 
            _trend_up, _trend_down,
            hi2_value=_hi2_val,
            garch_vol=_garch_vol,
            is_distribution=_is_dist,
            is_accumulation=_is_accum,
            hpi_signal=_hpi_result['hpi_signal'] if _hpi_result else None,
            hpi_divergence=_hpi_result['divergence'] if _hpi_result else False,
            zweig_signal=_zweig_scan['signal'] if '_zweig_scan' in dir() else None,
            rvi_val=_rvi_val2,
        )
        
        # === ВЕРДИКТ ===
        _dec_emoji = "🟢" if scanner['decision'] == 'LONG' else "🔴" if scanner['decision'] == 'SHORT' else "⚠️" if scanner.get('confidence') == 'нет данных' else "⚪"
        _dec_text = "ВХОД В ЛОНГ" if scanner['decision'] == 'LONG' else "ВХОД В ШОРТ" if scanner['decision'] == 'SHORT' else ("ВЕРДИКТ НЕ АКТУАЛЕН" if scanner.get('confidence') == 'нет данных' else "НЕ ВХОДИТЬ")
        if scanner.get('crisis_mode'):
            _dec_emoji = "🌪️"
            _dec_text += " | КРИЗИС-РЕЖИМ: приоритет 4H/1H, позиция 25%, стоп 2×"
        _long_s = scanner['score'] if scanner['decision'] == 'LONG' else (100 - scanner['score']) if scanner['decision'] == 'SHORT' else 50
        _short_s = 100 - _long_s

        col_v, col_m = st.columns([3, 2])
        with col_v:
            if scanner['decision'] == 'LONG':
                _color = '#00ff00' if scanner['score'] >= 80 else '#88ff00' if scanner['score'] >= 60 else '#ffff00'
                st.markdown(f"""<div style='background: {_color}22; border-left: 5px solid {_color}; padding: 15px; border-radius: 8px;'>
                <h2 style='margin:0; color: {_color};'>🎯 ОБЪЕДИНЁННЫЙ ВЕРДИКТ: {_dec_emoji} {_dec_text}</h2>
                <p style='margin:5px 0;'>Уверенность: {scanner['confidence']} | Скор: {scanner['score']}/100</p>
                </div>""", unsafe_allow_html=True)
            elif scanner['decision'] == 'SHORT':
                _color = '#ff0000' if scanner['score'] >= 80 else '#ff4444' if scanner['score'] >= 60 else '#ff8800'
                st.markdown(f"""<div style='background: {_color}22; border-left: 5px solid {_color}; padding: 15px; border-radius: 8px;'>
                <h2 style='margin:0; color: {_color};'>🎯 ОБЪЕДИНЁННЫЙ ВЕРДИКТ: {_dec_emoji} {_dec_text}</h2>
                <p style='margin:5px 0;'>Уверенность: {scanner['confidence']} | Скор: {scanner['score']}/100</p>
                </div>""", unsafe_allow_html=True)
            else:
                st.markdown(f"""<div style='background: #88888822; border-left: 5px solid #888888; padding: 15px; border-radius: 8px;'>
                <h2 style='margin:0; color: #aaaaaa;'>🎯 ОБЪЕДИНЁННЫЙ ВЕРДИКТ: {_dec_emoji} {_dec_text}</h2>
                <p style='margin:5px 0;'>Уверенность: {scanner['confidence']} | Скор: {scanner['score']}/100</p>
                </div>""", unsafe_allow_html=True)
            st.caption(scanner['recommendation'])
            # === СВЕТОФОР: ослабляющие факторы ===
            _factors = scanner.get('factors', {})
            _warnings = []
            # Дистрибуция
            if _factors.get('distr_mod', 0) < 0:
                _warnings.append("🔴 Дистрибуция — юрики продают, будь осторожнее в лонге")
            # HPI
            if _factors.get('hpi_mod', 0) < 0:
                _warnings.append("🟡 HPI: капитал уходит — рост может быть неустойчивым")
            elif _factors.get('hpi_mod', 0) > 0:
                _warnings.append("🟢 HPI подтверждает направление")
            # Zweig
            if _factors.get('zweig_mod', 0) < 0:
                _warnings.append("🟡 Рынок нестабилен (Zweig) — уменьши позицию")
            # HI2
            if _factors.get('hi2_penalty', 0) < 0:
                _warnings.append("🟡 Концентрация позиций высокая — риск манипуляции")
            # Перекупленность (из Renaissance Scanner)
            _fiz_buy = scanner.get('signals', {}).get('1D', {}).get('details', {}).get('fiz_buy', 0)
            if _fiz_buy > 80:
                _warnings.append("🔴 Перекупленность (fiz_buy > 80) — исторически 67% вероятность коррекции (GAZPF/IMOEXF)")
            # GARCH
            if _factors.get('garch_penalty', 0) < 0:
                _warnings.append("🟡 Волатильность повышена — стоп шире обычного")
            # RVI
            _rvi_val_factor = _factors.get('rvi_val')
            if _rvi_val_factor is not None:
                _warnings.append(f"📊 RVI={_rvi_val_factor:.1f} — индекс волатильности рынка")
            # Volume Spike
            if _factors.get('volume_mod', 0) > 0:
                _warnings.append(f"📊 Volume Spike! Аномальный объём (+{_factors['volume_mod']} к скору)")
            
            if _warnings:
                for _w in _warnings:
                    st.caption(_w)
            
            # === ОЦЕНКА РИСКА ===
            _total_mod = _factors.get('total_mod', 0)
            _score = scanner['score']
            if _score >= 70:
                _risk_pct = max(25, 100 + _total_mod * 2)
                _risk_level = "🟢 ПОНИЖЕННЫЙ РИСК"
                _risk_action = f"Можно входить. Рекомендуемая позиция: {_risk_pct:.0f}% от стандартной."
            elif _score >= 50:
                _risk_pct = max(15, 75 + _total_mod * 2)
                _risk_level = "🟡 СРЕДНИЙ РИСК"
                _risk_action = f"Входить осторожно. Позиция: {_risk_pct:.0f}% от стандартной."
            else:
                _risk_pct = max(5, 50 + _total_mod * 2)
                _risk_level = "🔴 ПОВЫШЕННЫЙ РИСК"
                _risk_action = f"Лучше воздержаться. Максимальная позиция: {_risk_pct:.0f}%."
            
            st.caption(f"{_risk_level}: {_risk_action}")
            
            # === СЕЗОННОСТЬ: предупреждение о дне недели ===
            from datetime import datetime
            _wd = datetime.now().weekday()
            _wd_names = ['Пн','Вт','Ср','Чт','Пт','Сб','Вс']
            if _wd == 3:
                st.caption("📅 Четверг — исторически худший день (win-rate 43%). Будь осторожнее.")
            elif _wd == 2:
                st.caption("📅 Среда — исторически лучший день (win-rate 53%). Хорошее время для входа.")
            elif _wd >= 6:
                st.caption("📅 Выходной — рынок закрыт, сигналы неактуальны.")
            
            # === VOLUME SPIKE: проверка аномалий объёма ===
            try:
                from My_Indicators.volume_analyzer import VolumeAnomalyDetector
                _vd = VolumeAnomalyDetector()
                _d1_file = DATA_ROOT / 'candles' / f'{selected_ticker}_D1.parquet'
                if _d1_file.exists():
                    _vdf = pd.read_parquet(_d1_file)
                    if 'volume' in _vdf.columns and len(_vdf) > 25:
                        _spikes = _vd.detect_spikes(_vdf['volume'])
                        if _spikes['spikes'].iloc[-1]:
                            st.caption("📊 Volume Spike! Аномальный объём — возможно движение цены (SV:75%, SI:65% win-rate).")
            except:
                pass
        with col_m:
            cols = st.columns(2)
            cols[0].metric("Лонг", f"{_long_s}/100")
            cols[1].metric("Шорт", f"{_short_s}/100")
        
        st.caption(f"Тренд D1: {scanner['trend']} | 1D: {scanner['signals']['1D']['signal']} | 4H: {scanner['signals']['4H']['signal']} | 1H: {scanner['signals']['1H']['signal']}")
            
        with st.expander("🔍 Факторы вердикта (как формируется решение)"):
            st.markdown(f"""
**Базовый ТФ-скор:** {scanner['factors']['tf_score']:.0f}/100 (1D=50%, 4H=30%, 1H=20%)
**Взвешенный сигнал:** {scanner['factors']['tf_weighted']:+.2f}

**Корректирующие факторы:**
- {scanner['factors']['hi2_note']}
- {scanner['factors']['garch_note']}
- {scanner['factors']['trend_note']}
- {scanner['factors']['distr_note']}
- {scanner['factors']['hpi_note']}
- {scanner['factors']['zweig_note']}

**Итого корректировка:** {scanner['factors']['total_mod']:+d}
**Финальный скор:** {scanner['score']}/100

**Zweig Filter:** объединяет режим рынка, TRIN, сессию и GARCH. BLOCKED = вход запрещён, CAUTION = штраф -5.
**Индекс Херрика (HPI):** объединяет Цену + Объём + Открытый интерес. Показывает приток/отток капитала. HPI>0 = деньги заходят, HPI<0 = деньги уходят. Дивергенция HPI = цена и потоки расходятся → предупреждение.
**Volume Spike Detector:** обнаруживает аномальные всплески объёма (Z-score > 2.5). На исторических данных: SV 75%, SI 65%, BR 64% win-rate после спайка. Подтверждает направление сигнала (+5 к скору).
                        """)
        
        with st.expander("🌪️ Что такое КРИЗИС-РЕЖИМ?"):
            st.markdown("""
**КРИЗИС-РЕЖИМ** — особый режим торговли при экстремальной волатильности.

**Триггеры (для фьючерсов):**
- **RVI > 40%** — волатильность выше критического порога
- **RVI > 70** — индекс волатильности рынка превысил норму

**Что меняется:**
| Параметр | Обычный | Кризис |
|----------|--------|-------|
| Веса ТФ | 1D:50%, 4H:30%, 1H:20% | 1D:20%, 4H:50%, 1H:30% |
| Порог LONG | 60 | 80 |
| Порог SHORT | 40 | 80 |
| Позиция | 100% | 25% |
| Стоп | 1× ATR | 2× ATR |
| Тейк | стандартный | 1.5× ATR |

**Запреты при кризисе:**
- HI2 > 500 — высокая концентрация
- Дивергенция HPI — капитал уходит против сигнала
- Низкий объём — нет ликвидности

**Логика:** Приоритет краткосрочным сигналам (4H, 1H). Дневные сигналы в кризис часто запаздывают.
            """)

        # === ТРИ ТАЙМФРЕЙМА ===
        st.markdown("---")
        # === ZWEIG MASTER FILTER ===
    _session_scan = get_session_status()
    tab1, tab2, tab3 = st.tabs(["📅 1D — Стратегия", "🕐 4H — Тактика", "⏱️ 1H — Точка входа"])
        
    with tab1:
        st.subheader(f"1D: {scanner['signals']['1D']['signal']} (скор: {scanner['signals']['1D']['score']}/100)")
        d1 = scanner['signals']['1D']['details']
        st.caption(f"fiz_buy: {d1.get('fiz_buy', '—')}% | Δ: {d1.get('fiz_delta', 0):+.2f}%")
        
        # === ДАННЫЕ ДЛЯ 1D АНАЛИЗА ===
        candle_file = DATA_ROOT / "candles" / f"{selected_ticker}_D1.parquet"
        df_d1 = pd.read_parquet(candle_file) if candle_file.exists() else None
        tradestats_file = DATA_ROOT / "tradestats" / f"{selected_ticker}_tradestats.parquet"
        df_ts = pd.read_parquet(tradestats_file) if tradestats_file.exists() else None
        atr_info, _ = calculate_atr(df_d1) if df_d1 is not None else (None, None)
        
        # HI2
        hi2_info = None
        hi2_value = None
        hi2_level = "—"
        hi2_emoji = "—"
        hi2_data = load_hi2_data()
        if hi2_data is not None:
            _hi2_lookup = selected_ticker
            if selected_ticker == 'BR': _hi2_lookup = 'BRN6'
            hi2_ticker = hi2_data[hi2_data['ticker'] == _hi2_lookup]
            if len(hi2_ticker) > 0:
                hi2_agressive = hi2_ticker[hi2_ticker['metric'] == 'hhi_agressive']
                if len(hi2_agressive) > 0:
                    hi2_sorted = hi2_agressive.sort_values('tradedate')
                    last_hi2 = hi2_sorted.iloc[-1]
                    hi2_value = last_hi2['value']
                    hi2_delta = None
                    if len(hi2_sorted) >= 2:
                        hi2_delta = hi2_value - hi2_sorted.iloc[-2]['value']
                    if hi2_value > 500:
                        hi2_level = "Экстремальная"
                        hi2_emoji = "🔴"
                    elif hi2_value > 150:
                        hi2_level = "Очень высокая"
                        hi2_emoji = "🔴"
                    elif hi2_value > 70:
                        hi2_level = "Высокая"
                        hi2_emoji = "🟡"
                    elif hi2_value > 40:
                        hi2_level = "Средняя"
                        hi2_emoji = "🟢"
                    else:
                        hi2_level = "Низкая"
                        hi2_emoji = "🟢"
                    hi2_info = {
                        'value': hi2_value,
                        'level': hi2_level,
                            'emoji': hi2_emoji,
                        'delta': hi2_delta
                    }
        
        # Сигналы (упрощённо, без полного calculate_signals)
        latest = df_analytics.iloc[-1] if df_analytics is not None else None
        
        # График fiz/yur
        if df_analytics is not None and len(df_analytics) > 5:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df_analytics['datetime'], y=df_analytics['fiz_buy_ratio'], mode='lines', name='Физ %', line=dict(color='#00BFFF')))
            fig.add_trace(go.Scatter(x=df_analytics['datetime'], y=df_analytics['yur_buy_ratio'], mode='lines', name='Юр %', line=dict(color='#FF6B6B')))
            fig.update_layout(height=300, template='plotly_dark', title='FutOI 1D')
            st.plotly_chart(fig, use_container_width=True)
        
        # Ключевые метрики
        if latest is not None:
            col1, col2, col3 = st.columns(3)
            fiz_long_pct = latest['pos_long_fiz'] / (latest['pos_long_fiz'] + latest['pos_short_fiz'] + 1) * 100
            yur_short_pct = latest['pos_short_yur'] / (latest['pos_long_yur'] + latest['pos_short_yur'] + 1) * 100
            with col1:
                st.metric("Открытый интерес", f"{abs(latest['phys_net']):,.0f}".replace(",", " "))
            with col2:
                st.metric("% физ", f"{latest['fiz_buy_ratio']:.1f}%")
            with col3:
                st.metric("% юр", f"{latest['yur_buy_ratio']:.1f}%")
        
        # HI2 и GARCH
        if hi2_value or atr_info:
            col_r1, col_r2 = st.columns(2)
            with col_r1:
                if hi2_value:
                    st.metric("HI2", f"{hi2_value:.0f}", delta=hi2_level)
            with col_r2:
                if df_d1 is not None:
                    garch_result = calculate_garch_for_ticker(df_d1, selected_ticker)
                    if garch_result.get('garch_vol'):
                        st.metric("GARCH", f"{garch_result['garch_vol']:.1f}%", delta=garch_result.get('trend', '—'))
        
        # Order Flow
        if df_ts is not None:
            ofi = calculate_ofi(df_ts)
            cd = calculate_cumulative_delta(df_ts)
            st.markdown("---")
            st.subheader("📊 Order Flow & Cumulative Delta")
            col_ofi1, col_ofi2, col_ofi3 = st.columns(3)
            with col_ofi1:
                ofi_val = ofi['ofi']
                emoji = "🟢" if ofi_val > 0.1 else "🔴" if ofi_val < -0.1 else "⚪"
                st.metric("OFI", f"{ofi_val:+.3f}", delta=f"{emoji} {ofi['pressure']}")
            with col_ofi2:
                delta_emoji = "📈" if cd['delta_trend'] == 'растёт' else "📉"
                st.metric("Cumulative Delta", f"{cd['cum_delta']:,.0f}".replace(",", " "), delta=f"{delta_emoji} {cd['delta_trend']}")
            with col_ofi3:
                div_text = "⚠️ Дивергенция!" if cd['divergence'] or ofi['divergence'] else "✅ Нет дивергенции"
                st.metric("Дивергенция", div_text)
        
        # === ИНДЕКС ВЫПЛАТ ХЕРРИКА (HPI) ===
        if df_d1 is not None:
            _oi_file = DATA_ROOT / "futoi" / f"{selected_ticker}_futoi.parquet"
            _df_oi = None
            if _oi_file.exists():
                _fut = pd.read_parquet(_oi_file)
                # Агрегируем ОИ по дням
                _fut['tradedate'] = pd.to_datetime(_fut['tradedate'])
                _oi_daily = _fut.groupby('tradedate').last().reset_index()
                if 'oi_close' not in _oi_daily.columns and 'pos' in _oi_daily.columns:
                    _oi_daily['oi_close'] = _oi_daily['pos'].abs()
                _df_oi = _oi_daily
            
            _hpi_result = calculate_hpi(df_d1, _df_oi)
            if _hpi_result:
                st.markdown("---")
                st.subheader("📊 Индекс выплат Херрика (HPI)")
                col_h1, col_h2, col_h3 = st.columns(3)
                with col_h1:
                    _hpi_emoji = "🟢" if _hpi_result['hpi_signal'] == 'LONG' else "🔴" if _hpi_result['hpi_signal'] == 'SHORT' else "⚪"
                    st.metric("HPI", f"{_hpi_result['hpi']:.2f}", delta=f"{_hpi_emoji} {_hpi_result['hpi_signal']}")
                with col_h2:
                    st.metric("Объём", f"{_hpi_result['volume']:,}".replace(",", " "))
                    with col_h3:
                        _oi_delta = "▲" if _hpi_result['oi_change'] > 0 else "▼" if _hpi_result['oi_change'] < 0 else "—"
                        st.metric("Δ ОИ", f"{_hpi_result['oi_change']:+,}".replace(",", " "))
                    
                    if _hpi_result.get('note'):
                        st.caption(f"ℹ️ {_hpi_result['note']}")
                    if _hpi_result['divergence']:
                        _hpi_val = _hpi_result['hpi']
                        if _hpi_val > 0:
                            _hpi_msg = f"⚠️ Дивергенция HPI: капитал заходит (HPI={_hpi_val:+.1f}), но цена не растёт — возможен скрытый набор позиции."
                        else:
                            _hpi_msg = f"⚠️ Дивергенция HPI: капитал уходит (HPI={_hpi_val:+.1f}), но цена не падает — рост может быть неустойчивым."
                        st.warning(_hpi_msg)
            
            # Уровни и риск-менеджмент
            if df_d1 is not None:
                _close = df_d1['close'].iloc[-1]
                _atr = atr_info['atr'] if atr_info else (_close * 0.01)
                _risk = calculate_risk(selected_ticker, _close, atr=_atr, deposit=_deposit)
                st.markdown("---")
                st.subheader("💰 Риск-менеджмент")
                col_rm1, col_rm2 = st.columns(2)
                with col_rm1:
                    st.metric("ГО (1 лот)", f"{_risk['go']:,.0f} ₽".replace(",", " "))
                with col_rm2:
                    st.metric("Стоимость контракта", f"{_risk['contract_cost']:,.0f} ₽".replace(",", " "))
        
            # === ТАБЛИЦА УЧАСТНИКОВ ===
            if latest is not None:
                st.markdown("---")
                st.subheader("👥 Участники рынка")
                fiz_pct = latest['fiz_buy_ratio']
                yur_pct = latest['yur_buy_ratio']
                is_distribution = latest['phys_net'] > 0 and latest['corp_net'] < 0
                is_accumulation = latest['phys_net'] < 0 and latest['corp_net'] > 0
                
                _lines = []
                _lines.append("| Группа | % | Доминирование | Действие |")
                _lines.append("| :--- | :--- | :--- | :--- |")
                
                fiz_dom = "Доминируют" if fiz_pct > 65 or fiz_pct < 35 else "—"
                yur_dom = "Доминируют" if yur_pct > 65 or yur_pct < 35 else "—"
                action_fiz = "Покупают" if latest['phys_net'] > 0 else "Продают"
                action_yur = "Покупают" if latest['corp_net'] > 0 else "Продают"
                
                _lines.append(f"| Физики | {fiz_pct:.1f}% покупателей | {fiz_dom} | {action_fiz} |")
                _lines.append(f"| Юрики | {yur_pct:.1f}% покупателей | {yur_dom} | {action_yur} |")
                
                if is_distribution:
                    _lines.append(f"| Общее | — | — | 🔴 Дистрибуция |")
                elif is_accumulation:
                    _lines.append(f"| Общее | — | — | 🟢 Аккумуляция |")
                else:
                    _lines.append(f"| Общее | — | — | — |")
                
                st.markdown("\n".join(_lines))
            
            # === УРОВНИ ===
            if df_d1 is not None:
                st.markdown("---")
                st.subheader("📐 Уровни (VP + FutOI + HI2)")
                _hi2_adv = load_hi2_data()
                _atr_val = atr_info['atr'] if atr_info else None
                adv_levels = calculate_advanced_levels(df_d1, df_analytics, _hi2_adv, selected_ticker, _atr_val)
                
                if adv_levels['support'] or adv_levels['resistance']:
                    col_s, col_r = st.columns(2)
                    with col_s:
                        if adv_levels['support']:
                            src = ', '.join(adv_levels['support_sources'])
                            strength = '💪' if adv_levels['support_strength'] == 'сильный' else '🤏'
                            st.metric("Поддержка", f"{adv_levels['support']:.2f}", delta=f"{strength} {src}")
                    with col_r:
                        if adv_levels['resistance']:
                            src = ', '.join(adv_levels['resistance_sources'])
                            strength = '💪' if adv_levels['resistance_strength'] == 'сильный' else '🤏'
                            st.metric("Сопротивление", f"{adv_levels['resistance']:.2f}", delta=f"{strength} {src}")
                    if adv_levels['poc']:
                        st.caption(f"🎯 POC: {adv_levels['poc']:.2f}")
            
            # === УРОВНИ ВХОДА/ВЫХОДА + КАЛЬКУЛЯТОР + ТРЕЙЛИНГ-СТОП ===
            if scanner['decision'] != 'WAIT':
                st.markdown("---")
                st.subheader("📐 Уровни входа/выхода")
                
                _atr_val = atr_info['atr'] if atr_info else 0.05
                _support = adv_levels.get('support', 0)
                _resistance = adv_levels.get('resistance', 0)
                _close = df_d1['close'].iloc[-1] if df_d1 is not None and len(df_d1) > 0 else 0
                
                if scanner['decision'] == 'LONG':
                    _entry = _support if _support > 0 else _close
                    _stop = _entry - _atr_val * 1.5
                    _target = _resistance if _resistance > _entry else _entry + _atr_val * 3
                else:
                    _entry = _resistance if _resistance > 0 else _close
                    _stop = _entry + _atr_val * 1.5
                    _target = _support if _support < _entry else _entry - _atr_val * 3
                
                col_e, col_s, col_t = st.columns(3)
                with col_e: st.metric("Вход", f"{_entry:.2f}")
                with col_s: st.metric("Стоп-лосс", f"{_stop:.2f}", delta=f"{abs(_entry - _stop):.2f}")
                with col_t:
                    _pot = abs(_target - _entry) / _entry * 100 if _entry > 0 else 0
                    st.metric("Цель", f"{_target:.2f}", delta=f"+{_pot:.1f}%" if _pot > 0 else None)
                
                _risk_rub = _deposit * _risk_pct / 100
                _lot = 1000 if selected_ticker in ['CNYRUBF', 'USDRUBF', 'EURRUBF'] else 10
                _risk_per_contract = abs(_entry - _stop) * _lot
                if _risk_per_contract > 0:
                    _position_size = int(_risk_rub / _risk_per_contract)
                    if _position_size > 0:
                        st.success(f"💰 Позиция: **{_position_size}** контрактов (риск {_risk_rub:,.0f} ₽ = {_risk_pct}% от {_deposit:,.0f} ₽)".replace(",", " "))
                
                with st.expander("🔒 Трейлинг-стоп", expanded=False):
                    _trail_activate = _entry + 2*_atr_val if scanner['decision'] == 'LONG' else _entry - 2*_atr_val
                    st.markdown(f"""
**Как работает:** после входа стоп подтягивается за ценой. При движении в плюс на 2×ATR → стоп на 1×ATR от цены.
**ATR:** {_atr_val:.2f} | **Стоп:** {_stop:.2f} | **Активация:** {_trail_activate:.2f}
                    """)
            
            # === ГРАФИК D1 С УРОВНЯМИ ===
            with st.expander("📈 График D1 с уровнями", expanded=False):
                _candle_file = DATA_ROOT / "candles" / f"{selected_ticker}_D1.parquet"
                if _candle_file.exists():
                    _df_d1_graph = pd.read_parquet(_candle_file)
                    if len(_df_d1_graph) > 0:
                        _df_d1_graph["begin"] = pd.to_datetime(_df_d1_graph["begin"])
                        _fig_g = go.Figure()
                        _fig_g.add_trace(go.Candlestick(x=_df_d1_graph["begin"], open=_df_d1_graph["open"], high=_df_d1_graph["high"], low=_df_d1_graph["low"], close=_df_d1_graph["close"], name="D1"))
                        if adv_levels.get("support"):
                            _fig_g.add_hline(y=adv_levels["support"], line_dash="dash", line_color="green", annotation_text=f"Поддержка: {adv_levels["support"]:.2f}")
                        if adv_levels.get("resistance"):
                            _fig_g.add_hline(y=adv_levels["resistance"], line_dash="dash", line_color="red", annotation_text=f"Сопротивление: {adv_levels["resistance"]:.2f}")
                        if adv_levels.get("poc"):
                            _fig_g.add_hline(y=adv_levels["poc"], line_dash="dot", line_color="white", annotation_text=f"POC: {adv_levels["poc"]:.2f}")
                        _fig_g.update_layout(height=400, template="plotly_dark", title=f"{selected_ticker} D1 с уровнями")
                        st.plotly_chart(_fig_g, use_container_width=True)
                else:
                    st.info("Нет данных свечей")


            with st.expander("🔔 MegaAlerts", expanded=False):
                _alerts = get_mega_alerts(selected_ticker, market='fo', days=2)
                if _alerts:
                    for _a in _alerts:
                        _sev = "🔴" if _a["severity"] == "high" else "🟡"
                        st.caption(f"{_a["time"]} | {_a["type"]}")
                else:
                    st.caption("Нет алертов")

        with tab2:
            st.subheader(f"4H: {scanner['signals']['4H']['signal']} (скор: {scanner['signals']['4H']['score']}/100)")
            d4 = scanner['signals']['4H']['details']
            st.caption(f"fiz_buy: {d4.get('fiz_buy', '—')}% | Δ: {d4.get('fiz_delta', 0):+.2f}%")
            
            # График fiz/yur (если есть данные)
            if df_4h is not None and len(df_4h) > 3:
                fig2 = go.Figure()
                fig2.add_trace(go.Scatter(x=df_4h['hour'], y=df_4h['fiz_buy_ratio'], mode='lines+markers', name='Физ %', line=dict(color='#00BFFF')))
                fig2.add_trace(go.Scatter(x=df_4h['hour'], y=df_4h['yur_buy_ratio'], mode='lines+markers', name='Юр %', line=dict(color='#FF6B6B')))
                fig2.update_layout(height=300, template='plotly_dark', title='FutOI 4H (накопление данных...)')
                st.plotly_chart(fig2, use_container_width=True)
                st.caption("ℹ️ Данных пока мало (сборщик запущен 17.06). Полноценный анализ будет доступен через 1-2 недели.")
            
            # Свечной график H1 (агрегируем до 4H)
            _h1_file = DATA_ROOT / "candles" / f"{selected_ticker}_H1.parquet"
            if _h1_file.exists():
                _h1_df = pd.read_parquet(_h1_file)
                if len(_h1_df) > 10:
                    _h1_df['begin'] = pd.to_datetime(_h1_df['begin'])
                    _h1_df = _h1_df.sort_values('begin')
                    # Агрегируем в 4H
                    _h1_df['h4_block'] = _h1_df['begin'].dt.floor('4h')
                    _h4_candles = _h1_df.groupby('h4_block').agg(
                        open=('open', 'first'),
                        high=('high', 'max'),
                        low=('low', 'min'),
                        close=('close', 'last'),
                        volume=('volume', 'sum')
                    ).reset_index()
                    
                    st.subheader("🕯️ Свечи 4H (из H1)")
                    _fig_h4 = go.Figure()
                    _fig_h4.add_trace(go.Candlestick(
                        x=_h4_candles['h4_block'],
                        open=_h4_candles['open'],
                        high=_h4_candles['high'],
                        low=_h4_candles['low'],
                        close=_h4_candles['close'],
                        name='4H'
                    ))
                    _fig_h4.update_layout(height=350, template='plotly_dark')
                    st.plotly_chart(_fig_h4, use_container_width=True)
                    
                    # Уровни VP на основе 4H свечей
                    if len(_h4_candles) >= 20:
                        _h4_candles['typical_price'] = (_h4_candles['high'] + _h4_candles['low'] + _h4_candles['close']) / 3
                        _vp = _h4_candles.groupby(_h4_candles['typical_price'].round(1))['volume'].sum().reset_index()
                        _vp = _vp.sort_values('volume', ascending=False)
                        if len(_vp) > 0:
                            _poc = _vp.iloc[0]['typical_price']
                            st.caption(f"🎯 POC (4H): {_poc:.2f} (макс. объём)")
        
        with tab3:
            st.subheader(f"1H: {scanner['signals']['1H']['signal']} (скор: {scanner['signals']['1H']['score']}/100)")
            d1h = scanner['signals']['1H']['details']
            st.caption(f"fiz_buy: {d1h.get('fiz_buy', '—')}% | Δ: {d1h.get('fiz_delta', 0):+.2f}%")
            
            # График fiz/yur 1H
            if df_1h is not None and len(df_1h) > 5:
                fig3 = go.Figure()
                fig3.add_trace(go.Scatter(x=df_1h['hour'], y=df_1h['fiz_buy_ratio'], mode='lines', name='Физ %', line=dict(color='#00BFFF')))
                fig3.add_trace(go.Scatter(x=df_1h['hour'], y=df_1h['yur_buy_ratio'], mode='lines', name='Юр %', line=dict(color='#FF6B6B')))
                fig3.update_layout(height=300, template='plotly_dark', title='FutOI 1H')
                st.plotly_chart(fig3, use_container_width=True)
            
            # Метрики 1H
            if df_1h is not None and len(df_1h) >= 2:
                _latest_1h = df_1h.iloc[-1]
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("% физ (1H)", f"{_latest_1h['fiz_buy_ratio']:.1f}%", delta=f"{_latest_1h['fiz_ratio_delta']:+.1f}%" if pd.notna(_latest_1h.get('fiz_ratio_delta')) else None)
                with col2:
                    st.metric("% юр (1H)", f"{_latest_1h['yur_buy_ratio']:.1f}%", delta=f"{_latest_1h['yur_ratio_delta']:+.1f}%" if pd.notna(_latest_1h.get('yur_ratio_delta')) else None)
                with col3:
                    _phys = _latest_1h['fiz_long'] - _latest_1h['fiz_short']
                    st.metric("Нетто физиков", f"{_phys:+,.0f}".replace(",", " "))
            
            # GARCH и тренд 1H
            _h1_file = DATA_ROOT / "candles" / f"{selected_ticker}_H1.parquet"
            if _h1_file.exists():
                _df_h1 = pd.read_parquet(_h1_file)
                if len(_df_h1) >= 20:
                    _garch_1h = calculate_garch_for_ticker(_df_h1, selected_ticker)
                    _df_h1['sma20'] = _df_h1['close'].rolling(20).mean()
                    _h1_trend = "📈 Бычий" if _df_h1['close'].iloc[-1] > _df_h1['sma20'].iloc[-1] * 1.002 else ("📉 Медвежий" if _df_h1['close'].iloc[-1] < _df_h1['sma20'].iloc[-1] * 0.998 else "◼ Боковик")
                    
                    col_r1, col_r2 = st.columns(2)
                    with col_r1:
                        st.metric("GARCH (1H)", f"{_garch_1h.get('garch_vol', 0):.1f}%", delta=_garch_1h.get('trend', '—'))
                    with col_r2:
                        st.metric("Тренд 1H", _h1_trend)
            
            # Дельта за 1 час (таблица)
            if df_1h is not None and len(df_1h) >= 3:
                st.markdown("---")
                with st.expander("📊 Дельта за 1 час (последние 10)", expanded=False):
                    _delta_df = df_1h.tail(10)[["hour", "fiz_ratio_delta", "yur_ratio_delta"]].copy()
                    _delta_lines = []
                    for _, row in _delta_df.iterrows():
                        fiz_d = row['fiz_ratio_delta']
                        yur_d = row['yur_ratio_delta']
                        f_arrow = "▲" if fiz_d > 0 else "▼" if fiz_d < 0 else "▬"
                        y_arrow = "▲" if yur_d > 0 else "▼" if yur_d < 0 else "▬"
                        if fiz_d > 0.05 and yur_d < -0.05:
                            _action = "Физики покупают, юрики продают"
                        elif fiz_d < -0.05 and yur_d > 0.05:
                            _action = "Физики продают, юрики покупают"
                        elif fiz_d > 0.05 and yur_d > 0.05:
                            _action = "Обе группы покупают"
                        elif fiz_d < -0.05 and yur_d < -0.05:
                            _action = "Обе группы продают"
                        else:
                            _action = "Нейтрально"
                        _t = pd.to_datetime(row['hour']).strftime("%H:%M")
                        _delta_lines.append(f"{_t} Физ:{f_arrow}{abs(fiz_d):.1f}% Юр:{y_arrow}{abs(yur_d):.1f}% → {_action}")
                    _delta_text = "\n".join(_delta_lines)
                    st.text(_delta_text)
    
    st.markdown("---")

elif page == "📊 Парная торговля":
    st.title("📊 Парная торговля")
    st.caption("Статистический арбитраж: оптимизированные пары на M10/H1/H4/D1")
    
    # Загрузка конфигурации пар
    _config_path = Path("/root/finlab/FinLabPy/My_Indicators/pairs_config.json")
    if _config_path.exists():
        with open(_config_path, 'r') as f:
            _pairs_config = json.load(f)
    else:
        _pairs_config = {"pairs": {}}
    
    # Таймфреймы для выбора
    TIMEFRAMES = ['M10', 'H1', 'H4', 'D1']
    _selected_tf = st.selectbox("📅 Таймфрейм", TIMEFRAMES, index=0)
    
    # Собираем все пары для выбранного ТФ
    _available_pairs = []
    for _pair_name, _pair_data in _pairs_config.get('pairs', {}).items():
        if _selected_tf == 'D1':
            # Для D1 берем пары без суффикса и с _D1
            if '_M10' not in _pair_name and '_H1' not in _pair_name and '_H4' not in _pair_name:
                _available_pairs.append(_pair_name)
        else:
            if _pair_name.endswith(f"_{_selected_tf}"):
                _available_pairs.append(_pair_name)
    
    if not _available_pairs:
        st.warning(f"Нет оптимизированных пар для таймфрейма {_selected_tf}")
    else:
        # Сводная таблица
        st.subheader("📊 Сводная таблица пар")
        
        _table_data = []
        for _pair_name in sorted(_available_pairs):
            _pair_data = _pairs_config['pairs'][_pair_name]
            _test_metrics = _pair_data.get('test_metrics', {})
            _adf = _pair_data.get('adf', {})
            
            # Определяем статус
            _is_stationary = _adf.get('is_stationary', False)
            _win_rate = _test_metrics.get('win_rate', 0)
            _pnl = _test_metrics.get('total_pnl', 0)
            _sharpe = _test_metrics.get('sharpe', 0)
            _num_trades = _test_metrics.get('num_trades', 0)
            
            # Статус
            _adf_pvalue = _adf.get('p_value', 1.0)
            if _adf_pvalue < 0.05 and _win_rate > 0.55 and _pnl > 0:
                _status = "🟢 Активна"
            elif _win_rate > 0.55 and _pnl > 0:
                _status = "🟡 Перспективна"
            else:
                _status = "🔴 Неактивна"
            
            _table_data.append({
                'Пара': _pair_name.replace(f"_{_selected_tf}", ""),
                'Статус': _status,
                'Сделки': _num_trades,
                'Win Rate': f"{_win_rate*100:.1f}%",
                'PnL': f"{_pnl:.4f}",
                'Sharpe': _sharpe,
                'ADF p-value': _adf.get('p_value', 'N/A'),
                'Стационарность': '✅' if _is_stationary else '❌',
                'Параметры': f"w={_pair_data.get('best_params', {}).get('window', '?')}, "
                           f"e={_pair_data.get('best_params', {}).get('entry_z', '?')}, "
                           f"x={_pair_data.get('best_params', {}).get('exit_z', '?')}"
            })
        
        if _table_data:
            _df_table = pd.DataFrame(_table_data)
            st.dataframe(_df_table, use_container_width=True, hide_index=True)
        
        # Выбор пары для детального анализа
        st.markdown("---")
        st.subheader("🔍 Детальный анализ пары")
        
        _selected_pair = st.selectbox("Выберите пару", sorted(_available_pairs))
        
        if _selected_pair:
            _pair_data = _pairs_config['pairs'][_selected_pair]
            _best_params = _pair_data.get('best_params', {})
            _window = _best_params.get('window', 20)
            _entry_z = _best_params.get('entry_z', 2.0)
            _exit_z = _best_params.get('exit_z', 0.5)
            
            # Загружаем данные
            _base_pair = _selected_pair
            if _selected_tf == 'D1':
                _base_pair = _selected_pair  # уже без суффикса
            else:
                _base_pair = _selected_pair.replace(f"_{_selected_tf}", "")
            if '-' in _base_pair:
                _ticker_a, _ticker_b = _base_pair.split('-')
            else:
                _ticker_a, _ticker_b = _base_pair, _base_pair
            
            _file_a = DATA_ROOT / "candles" / f"{_ticker_a}_{_selected_tf}.parquet"
            _file_b = DATA_ROOT / "candles" / f"{_ticker_b}_{_selected_tf}.parquet"
            
            if _file_a.exists() and _file_b.exists():
                _df_a = pd.read_parquet(_file_a)
                _df_b = pd.read_parquet(_file_b)
                
                # Рассчитываем спред и Z-score с оптимизированными параметрами
                _result = analyze_pair(_df_a, _df_b, window=_window)
                
                if _result:
                    # Метрики
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("Z-score", f"{_result['zscore']:.2f}")
                    with col2:
                        st.metric("Корреляция", f"{_result['correlation']:.3f}")
                    with col3:
                        # Пересчитываем half-life в человекочитаемые единицы
                        _half_life = _result['half_life']
                        if _selected_tf == 'M10':
                            _half_life_hours = _half_life * 10 / 60
                            _half_life_text = f"{_half_life_hours:.1f} ч"
                        elif _selected_tf == 'H1':
                            _half_life_text = f"{_half_life:.1f} ч"
                        elif _selected_tf == 'H4':
                            _half_life_text = f"{_half_life * 4:.1f} ч"
                        else:
                            _half_life_text = f"{_half_life:.1f} дн"
                        st.metric("Half-life", _half_life_text)
                    with col4:
                        _test_m = _pair_data.get('test_metrics', {})
                        st.metric("Win Rate (тест)", f"{_test_m.get('win_rate', 0)*100:.1f}%")
                    
                    # Сигнал
                    st.markdown("---")
                    if _result['signal'] == "SHORT_SPREAD":
                        st.error(f"🎯 СИГНАЛ: 🔴 ШОРТ спреда — {_result['action']}")
                    elif _result['signal'] == "LONG_SPREAD":
                        st.success(f"🎯 СИГНАЛ: 🟢 ЛОНГ спреда — {_result['action']}")
                    else:
                        st.info(f"🎯 СИГНАЛ: ⚪ НЕЙТРАЛЬНО — {_result['action']}")
                    
                    # График Z-score с оптимизированными уровнями
                    st.markdown("---")
                    st.subheader(f"📊 Z-score (оптимизированные параметры: window={_window}, entry=±{_entry_z}, exit=±{_exit_z})")
                    _merged = _result['merged']
                    _zscore = _result['zscore_series']
                    
                    fig_z = go.Figure()
                    fig_z.add_trace(go.Scatter(
                        x=_merged['date'], y=_zscore, mode='lines', 
                        name='Z-score', line=dict(color='#FFD700', width=2)
                    ))
                    fig_z.add_hline(y=_entry_z, line_dash="dash", line_color="red", annotation_text=f"+{_entry_z}")
                    fig_z.add_hline(y=-_entry_z, line_dash="dash", line_color="green", annotation_text=f"-{_entry_z}")
                    fig_z.add_hline(y=_exit_z, line_dash="dot", line_color="orange", annotation_text=f"+{_exit_z}")
                    fig_z.add_hline(y=-_exit_z, line_dash="dot", line_color="lightgreen", annotation_text=f"-{_exit_z}")
                    fig_z.add_hline(y=0, line_dash="solid", line_color="gray")
                    fig_z.update_layout(height=400, template='plotly_dark', title='Z-score спреда')
                    st.plotly_chart(fig_z, use_container_width=True)
                    
                    # График спреда
                    st.subheader("📊 Спред")
                    _spread = _result['spread_series']
                    fig_s = go.Figure()
                    fig_s.add_trace(go.Scatter(
                        x=_merged['date'], y=_spread, mode='lines', 
                        name='Спред', line=dict(color='#00BFFF', width=2)
                    ))
                    _mean = _spread.mean()
                    _std = _spread.std()
                    fig_s.add_hline(y=_mean, line_dash="dash", line_color="white", annotation_text=f"Среднее: {_mean:.4f}")
                    fig_s.add_hline(y=_mean + _entry_z * _std, line_dash="dash", line_color="red", annotation_text=f"+{_entry_z}σ")
                    fig_s.add_hline(y=_mean - _entry_z * _std, line_dash="dash", line_color="green", annotation_text=f"-{_entry_z}σ")
                    fig_s.update_layout(height=350, template='plotly_dark', title='Спред с уровнями входа')
                    st.plotly_chart(fig_s, use_container_width=True)
                    
                    # Статистика
                    st.markdown("---")
                    st.subheader("📈 Статистика пары")
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        _adf_info = _pair_data.get('adf', {})
                        st.metric("ADF p-value", _adf_info.get('p_value', 'N/A'))
                    with col2:
                        _coint_info = _pair_data.get('cointegration', {})
                        st.metric("Коинтеграция p-value", _coint_info.get('p_value', 'N/A'))
                    with col3:
                        st.metric("Train Sharpe", _pair_data.get('train_score', 0))
                else:
                    st.warning("Недостаточно данных для анализа")
            else:
                st.error(f"Нет данных: {_ticker_a}_{_selected_tf} или {_ticker_b}_{_selected_tf}")

elif page == "📊 Скринер акций":
    st.title("📊 Скринер акций")
    st.caption("Комбинированный сигнал (HI2 + ADX + тренд)")
    
    # === ТЕМПЕРАТУРА РЫНКА АКЦИЙ ===
    with st.expander("🌡️ Температура рынка (акции)", expanded=True):
        st.caption("На основе средних ADX, Choppiness, RVI по акциям")
        
        _stock_adx = []
        _stock_chop = []
        _stock_garch = []
        
        try:
            from My_Indicators.stock_screener import calculate_adx, calculate_choppiness
            for _t in ['SBER', 'GAZP', 'GMKN', 'LKOH', 'HYDR', 'IRAO', 'PLZL', 'ROSN', 'TATN', 'VTBR']:
                _d1f = DATA_ROOT / "candles" / f"{_t}_D1.parquet"
                if _d1f.exists():
                    _df = pd.read_parquet(_d1f)
                    if len(_df) >= 30:
                        _stock_adx.append(calculate_adx(_df).iloc[-1])
                        _stock_chop.append(calculate_choppiness(_df).iloc[-1])
                        try:
                            _gr = calculate_garch_for_ticker(_df, _t)
                            _stock_garch.append(_gr.get('garch_vol', 0))
                        except:
                            pass
        except:
            pass
        
        _avg_adx_s = sum(_stock_adx) / len(_stock_adx) if _stock_adx else 0
        _avg_chop_s = sum(_stock_chop) / len(_stock_chop) if _stock_chop else 50
        _rvi_f = DATA_ROOT / 'sector_indices' / 'RVI_D1.parquet'
        if _rvi_f.exists():
            _rvi_df_s = pd.read_parquet(_rvi_f)
            _avg_garch_s = _rvi_df_s['close'].iloc[-1] if len(_rvi_df_s) > 0 else 0
        else:
            _avg_garch_s = 0
        
        _df_idx_s = pd.DataFrame({'adx': [_avg_adx_s], 'choppiness': [_avg_chop_s]})
        _regime_s = get_market_regime(df_indices=_df_idx_s, garch_vol=_avg_garch_s)
        
        _emoji_s = "🚀" if _regime_s['regime'] == 'TREND' else "🔄" if _regime_s['regime'] == 'FLAT' else "🌪️" if _regime_s['regime'] == 'CRISIS' else "⚠️"
        
        col_s1, col_s2, col_s3 = st.columns(3)
        with col_s1:
            st.metric("Режим", f"{_emoji_s} {_regime_s['regime']}", delta=f"Скор: {_regime_s['score']}/100")
        with col_s2:
            st.metric("Уровень риска", f"{_regime_s['risk_level']}/100")
        with col_s3:
            st.metric("RVI (индекс волатильности, пункты)", f"{_avg_garch_s:.1f} п.")
        
        _session_s = get_session_status()
        st.caption(f"📊 Сессия: {_session_s['label']} | Ликвидность: {_session_s['liquidity']:.0%}")
        if _session_s['warning']:
            st.warning(f"⚠️ {_session_s['warning']}")
        
        with st.expander("ℹ️ О торговых сессиях"):
            st.markdown("""
**Время торгов на MOEX (МСК):**
| Период | Время | Ликвидность | Особенности |
|--------|-------|:---:|-----------|
| Основная сессия | 10:00–18:45 | 🟢 Высокая | Лучшее время для входа |
| Открытие | 10:00–10:30 | 🟡 Средняя | Высокая волатильность |
| Обед | 12:00–13:00 | 🔴 Низкая | Мало объёмов |
| Закрытие | 18:30–18:45 | 🟡 Средняя | Закрытие позиций |
| Вечерняя сессия | 19:00–23:50 | 🔴 Низкая | Широкие спреды |

**Рекомендации:**
- 🟢 Активная сессия — лучшее время для входа
- 🔴 Низкая ликвидность — воздержаться или уменьшить позицию
            """)
        
        st.caption(_regime_s['recommendation'])
        if _regime_s['reasons']:
            for _r in _regime_s['reasons']:
                st.caption(f"• {_r}")
        
        # === ИНДЕКС АРМСА (TRIN) ===
        # Собираем все тикеры для TRIN (стандартные + кастомные)
        _all_tickers = load_stock_tickers()
        _custom_f = DATA_ROOT / "custom_stocks.txt"
        if _custom_f.exists():
            with open(_custom_f) as f:
                for _line in f:
                    _t = _line.strip()
                    if _t and _t not in _all_tickers:
                        _all_tickers.append(_t)
        _trin = calculate_trin(tickers=_all_tickers)
        st.markdown("---")
        st.subheader("📊 Индекс Армса (TRIN)")
        col_t1, col_t2, col_t3 = st.columns(3)
        with col_t1:
            st.metric("TRIN", f"{_trin['trin']:.2f}")
        with col_t2:
            _trin_emoji = "🟢" if _trin['signal'] == 'BULLISH' else "🔴" if _trin['signal'] == 'BEARISH' else "⚪"
            st.metric("Сигнал", f"{_trin_emoji} {_trin['signal']}")
        with col_t3:
            st.metric("Уровень", _trin['level'])
        st.caption(f"📝 {_trin['note']}")
        st.caption(f"Выросло: {_trin['advancing']} | Упало: {_trin['declining']} | Объём ▲: {_trin['adv_volume']:,} | Объём ▼: {_trin['dec_volume']:,}".replace(",", " "))
        
        # === ZWEIG MASTER FILTER ===
        _zweig = get_zweig_signal(_regime_s, _trin['trin'] if _trin else None, _session_s, _avg_garch_s)
        st.markdown("---")
        st.subheader(f"{_zweig['emoji']} {_zweig['label']}")
        for _r in _zweig['reasons']:
            st.caption(f"• {_r}")
        
        with st.expander("ℹ️ Что такое Zweig Filter?"):
            st.markdown("""
**Zweig Master Filter** — главный разрешающий сигнал. Объединяет все рыночные фильтры в одно решение.

**Учитывает:**
- 🌡️ Режим рынка (TREND/FLAT/CRISIS)
- 📊 TRIN (ширина рынка)
- 🕐 Торговую сессию (ликвидность)
- 📈 GARCH (волатильность)

**Сигналы:**
- ✅ **РАЗРЕШЕНО** — все фильтры чисты, можно торговать
- ⚠️ **ОСТОРОЖНО** — есть предупреждающие факторы
- ⛔ **ЗАПРЕЩЕНО** — рынок закрыт или кризис

**Основан на философии Мартина Цвейга:** "Не борись с рынком. Если фильтры против тебя — не входи."
            """)
        
        with st.expander("ℹ️ Как работает TRIN?"):
            st.markdown("""
**Индекс Армса (TRIN)** измеряет ширину рынка — соотношение растущих и падающих акций к их объёмам.

**Формула:** `TRIN = (Выросшие / Упавшие) / (Объём выросших / Объём упавших)`

**Расчёт:** на основе 12 акций из скринера (SBER, GAZP, GMKN, LKOH, HYDR, IRAO, PLZL, ROSN, TATN, VTBR, AFKS, T)

**Значения:**
| TRIN | Сигнал | Что значит |
|------|--------|-----------|
| < 0.5 | 🔴 Экстремальная перекупленность | Рынок перегрет, возможна коррекция |
| 0.5-0.8 | 🟢 Перекупленность | Объём в растущих — бычий сигнал |
| 0.8-1.0 | 🟢 Умеренно бычий | Покупатели контролируют |
| 1.0-1.2 | 🟡 Умеренно медвежий | Продавцы начинают давить |
| 1.2-1.5 | 🟠 Медвежий | Объём в падающих |
| > 1.5 | 🔴 Экстремальная перепроданность | Паника, возможен отскок |

**Важно:** TRIN — это **противоположный** индикатор. Экстремальные значения часто предшествуют развороту.
            """)
        
        with st.expander("🌪️ Что такое КРИЗИС-РЕЖИМ?"):
            st.markdown("""
**КРИЗИС-РЕЖИМ** — особый режим торговли, когда рынок находится в состоянии экстремальной волатильности.

**Триггеры включения:**
- **RVI > 40%** — волатильность акции/рынка превысила критический порог
- **TRIN < 0.5 или > 1.5** (только для акций) — экстремальная перекупленность/перепроданность рынка
- **RVI > 70** (только для фьючерсов) — индекс волатильности выше критического уровня

**Что меняется в кризис-режиме:**
| Параметр | Обычный режим | Кризис-режим |
|----------|--------------|-------------|
| Веса ТФ | D1:50%, 4H:30%, 1H:20% | D1:20%, 4H:50%, 1H:30% |
| Порог входа | 60 (LONG) / 40 (SHORT) | 80 |
| Позиция | 100% стандартной | 25% |
| Стоп | 1× ATR | 2× ATR |
| Тейк | стандартный | 1.5× ATR |

**Логика:**
В кризис приоритет отдаётся краткосрочным сигналам (4H, 1H), а не дневным. Дневные сигналы в кризис часто запаздывают.

**Запреты:**
- HI2 > 500 — концентрация позиций слишком высока
- Дивергенция HPI — капитал уходит против сигнала
- Низкий объём — недостаточно ликвидности для безопасного входа

**Важно:** В кризис-режиме лучше сохранить капитал, чем пытаться заработать. Саймонс говорил: "Когда рынок сходит с ума — не торгуй."
            """)

        with st.expander("ℹ️ Что это значит?"):
            st.markdown("""
**Температура рынка акций** — на основе 10 ликвидных акций MOEX.

**Режимы:**
- 🚀 **TREND** — рынок движется, сигналы надёжны
- 🔄 **FLAT** — боковик, не входить
- 🌪️ **CRISIS** — экстремальная волатильность, запрет входа
            """)
    st.caption("💡 Режим: тип рынка (ADX=сила тренда, Chop=трендовость). Цвета: 🟢 благоприятно, 🟡/🟠 умеренно, 🔴 неблагоприятно, ⚪ нейтрально.")
    
    with st.expander("ℹ️ Как анализировать скринер?"):
        st.markdown("""
**🎯 На что смотреть в первую очередь:**
1. **Режим** — можно ли вообще входить?
   - 🚀 Тренд (ADX>25, Chop<38) → рынок движется, сигналы надёжны
   - ⚠️ Переходный → неопределённость, сигналы могут быть ложными
   - 🔄 Флэт (ADX<20, Chop>62) → рынок в боковике, не входить
2. **Комбинированный сигнал** — направление: LONG (покупка) или SHORT (продажа)
3. **HI2** — концентрация позиций:
   - Высокая/Экстремальная (>150) → крупные игроки активны, движение может быть сильным
   - Низкая/Средняя (<150) → позиции распылены, движение может быть вялым

**📊 Как интерпретировать:**
- **🚀 Тренд + Сигнал SHORT + HI2 высокий** → надёжный сигнал на продажу
- **🚀 Тренд + Сигнал LONG + HI2 высокий** → надёжный сигнал на покупку
- **⚠️ Переходный** → ждать, когда рынок определится
- **🔄 Флэт** → не торговать, ждать пробоя

**⚡ Примеры:**
- VTBR: 🚀 Тренд (ADX 73, Chop 17) — сильный тренд, Сигнал SHORT надёжен
- SBER: ⚠️ Переходный (ADX 7, Chop 41) — тренда нет, сигнал SHORT ненадёжен
- ROSN: 🚀 Тренд (ADX 34, Chop 20) + HI2 низкий (58) — тренд есть, но позиции распылены

**🔍 Детали индикаторов:**
- **ADX** — сила тренда. >25 = сильный, 20-25 = средний, <20 = слабый
- **Choppiness** — трендовость. <38 = тренд, 38-62 = переход, >62 = флэт
- **ATR%** — волатильность. <1% = низкая, 1-2.5% = средняя, >2.5% = высокая
- **HI2** — концентрация. <70 = низкая, 70-150 = средняя, 150-500 = высокая, >500 = экстремальная

**🎯 Скор надёжности (Score 0-100):**
Рассчитывается на основе четырёх факторов:
| Фактор | Вес | Условие для максимума |
|--------|-----|----------------------|
| Режим | 35% | 🚀 Тренд = 35, ⚠️ Переход = 15, 🔄 Флэт = 0 |
| ADX | 25% | >40 = 25, >25 = 20, >20 = 10, <20 = 0 |
| HI2 | 25% | Экстр. (>500) = 25, Высокая = 20, Средняя = 10, Низкая = 5 |
| Комбинированный сигнал | 15% | Есть сигнал = 15, нет = 0 |

**Уровни сигнала:**
- 🔥 95-100 — идеальный: все факторы на максимуме, лучший момент для входа
- ✅ 80-94 — сильный: большинство факторов подтверждают, можно входить
- 👀 60-79 — умеренный: есть слабые места, входить с осторожностью
- ⏳ 40-59 — слабый: много противоречий, лучше ждать
- ❌ 0-39 — не входить: сигнал ненадёжен
        """)
    
    # Стандартный список + пользовательские тикеры
    _default_stocks = load_stock_tickers()
    
    # Загружаем пользовательские тикеры из файла
    _custom_file = DATA_ROOT / "custom_stocks.txt"
    _custom_stocks = []
    if _custom_file.exists():
        with open(_custom_file) as f:
            _custom_stocks = [line.strip() for line in f if line.strip()]
    
    STOCK_TICKERS = _default_stocks + _custom_stocks
    
    # === ДОБАВЛЕНИЕ / УДАЛЕНИЕ ТИКЕРОВ ===
    col_add, col_del = st.columns([3, 2])
    
    with col_add:
        _new_ticker = st.text_input("Добавить тикер", placeholder="Например: NVTK", key="new_ticker").upper()
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("📊 Добавить в скринер", key="add_screener"):
                if _new_ticker and _new_ticker not in _default_stocks:
                    # Собираем D1-свечи
                    try:
                        import requests
                        from datetime import datetime, timedelta
                        url = f"https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities/{_new_ticker}/candles.json"
                        resp = requests.get(url, params={
                            'from': (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d'),
                            'till': datetime.now().strftime('%Y-%m-%d'),
                            'interval': 24
                        })
                        if resp.status_code == 200 and 'candles' in resp.json():
                            data = resp.json()['candles']
                            if data['data']:
                                df_new = pd.DataFrame(data['data'], columns=data['columns'])
                                f = DATA_ROOT / "candles" / f"{_new_ticker}_D1.parquet"
                                df_new.to_parquet(f, index=False)
                                
                                # Добавляем в tickers_config.json
                                _cfg_path = Path('/root/finlab/FinLabPy/DataCollectors/tickers_config.json')
                                if _cfg_path.exists():
                                    with open(_cfg_path) as cf:
                                        _cfg = json.load(cf)
                                    if _new_ticker not in _cfg.get('stocks', []):
                                        _cfg['stocks'].append(_new_ticker)
                                        with open(_cfg_path, 'w') as cf:
                                            json.dump(_cfg, cf, indent=2, ensure_ascii=False)

                                # Добавляем в custom_stocks
                                _custom_stocks.append(_new_ticker)
                                with open(_custom_file, 'w') as f_out:
                                    f_out.write("\n".join(_custom_stocks))

                                # Добавляем в candles_collector
                                from pathlib import Path
                                _cc = Path('/root/finlab/FinLabPy/DataCollectors/candles_collector.py')
                                if _cc.exists():
                                    with open(_cc) as cf:
                                        _ct = cf.read()
                                    if _new_ticker not in _ct:
                                        _ct = _ct.replace("STOCKS = {", f"STOCKS = {{\n    '{_new_ticker}': 'TQBR',")
                                        with open(_cc, 'w') as cf:
                                            cf.write(_ct)

                                st.success(f"✅ {_new_ticker} добавлен! ({len(df_new)} свечей)")
                                st.rerun()
                            else:
                                st.error(f"❌ {_new_ticker}: нет данных")
                        else:
                            st.error(f"❌ {_new_ticker}: не найден на MOEX")
                    except Exception as e:
                        st.error(f"❌ Ошибка: {e}")
                elif _new_ticker in _default_stocks:
                    st.warning(f"⚠️ {_new_ticker} уже в скринере")
    
    with col_del:
        if _custom_stocks:
            _del_ticker = st.selectbox("Удалить тикер", [""] + _custom_stocks, key="del_ticker")
            if _del_ticker and st.button("🗑️ Удалить из скринера", key="del_btn"):
                _custom_stocks.remove(_del_ticker)
                with open(_custom_file, 'w') as f:
                    f.write("\n".join(_custom_stocks))
                st.success(f"🗑️ {_del_ticker} удалён из скринера")
                st.rerun()
        else:
            st.caption("Нет пользовательских тикеров")
    
    st.markdown("---")
    
    rows = []
    for ticker in STOCK_TICKERS:
        try:
            d1_file = DATA_ROOT / "candles" / f"{ticker}_D1.parquet"
            if not d1_file.exists():
                continue
            
            df_d1 = pd.read_parquet(d1_file)
            
            # HI2 для акции
            df_hi2 = None
            hi2_file = DATA_ROOT / "hi2" / f"{ticker}_hi2.parquet"
            if hi2_file.exists():
                df_hi2 = pd.read_parquet(hi2_file)
            
            # Трёхтаймфреймовый анализ
            _df_4h = None
            _df_1h = None
            _h4_file = DATA_ROOT / "candles" / f"{ticker}_H1.parquet"  # Агрегируем из H1
            _h1_file = DATA_ROOT / "candles" / f"{ticker}_H1.parquet"
            
            if _h1_file.exists():
                _h1_df = pd.read_parquet(_h1_file)
                if len(_h1_df) > 30:
                    _h1_df['begin'] = pd.to_datetime(_h1_df['begin'])
                    _h1_df = _h1_df.sort_values('begin')
                    _df_1h = _h1_df
                    
                    # Агрегируем в 4H
                    _h1_df['h4_block'] = _h1_df['begin'].dt.floor('4h')
                    _df_4h = _h1_df.groupby('h4_block').agg(
                        open=('open', 'first'),
                        high=('high', 'max'),
                        low=('low', 'min'),
                        close=('close', 'last'),
                        volume=('volume', 'sum')
                    ).reset_index().rename(columns={'h4_block': 'begin'})
            
            # Объединённый вердикт
            _garch_vol = 0
            try:
                from My_Indicators.garch_indicator import calculate_garch_for_ticker
                _gr = calculate_garch_for_ticker(df_d1, ticker)
                _garch_vol = _gr.get('garch_vol', 0)
            except:
                pass
            
            _hi2_val = None
            if df_hi2 is not None:
                _hi2_agr = df_hi2[df_hi2['metric'] == 'hhi_agressive']
                if len(_hi2_agr) > 0:
                    _hi2_val = _hi2_agr.sort_values('tradedate').iloc[-1]['value']
            
            # Секторальный анализ
            _sector_trend = None
            _sector_signal = '—'
            _sector_file = None
            _stock_to_sector = {'GMKN': 'MOEXMM', 'PLZL': 'MOEXMM', 'SBER': 'MOEXFN', 'VTBR': 'MOEXFN', 'T': 'MOEXFN',
                              'GAZP': 'MOEXOG', 'LKOH': 'MOEXOG', 'ROSN': 'MOEXOG', 'TATN': 'MOEXOG',
                              'HYDR': 'MOEXEU', 'IRAO': 'MOEXEU', 'AFKS': 'MOEXTL', 'AFLT': 'MOEXTL', 'YDEX': 'MOEXTL', 'RUAL': 'MOEXMM'}
            if ticker in _stock_to_sector:
                _sector_file = DATA_ROOT / "sector_indices" / f"{_stock_to_sector[ticker]}_D1.parquet"
                if _sector_file.exists():
                    _df_sector = pd.read_parquet(_sector_file)
                    _sector_result = analyze_vs_sector(df_d1, _df_sector)
                    if _sector_result:
                        _sector_trend = _sector_result['sector_trend']
                        _sector_signal = _sector_result['signal']
            
            # Доп. параметры для вердикта
            _chop_val = None; _adx_val = None; _atr_pct = 1.0; _rel_str = 1.0
            try:
                from My_Indicators.stock_screener import calculate_adx, calculate_choppiness
                _adx_series = calculate_adx(df_d1)
                _chop_series = calculate_choppiness(df_d1)
                _adx_val = _adx_series.iloc[-1] if len(_adx_series) > 0 else None
                _chop_val = _chop_series.iloc[-1] if len(_chop_series) > 0 else None
                _tr = pd.DataFrame({'h_l': df_d1['high'] - df_d1['low'], 'h_c': abs(df_d1['high'] - df_d1['close'].shift()), 'l_c': abs(df_d1['low'] - df_d1['close'].shift())}).max(axis=1)
                _atr_pct = (_tr.rolling(14).mean().iloc[-1] / df_d1['close'].iloc[-1] * 100) if df_d1['close'].iloc[-1] > 0 else 1.0
            except:
                pass
            if _sector_result:
                _rel_str = _sector_result.get('relative_strength', 1.0)
            
            # Volume spike
            _vol_sp2 = False
            try:
                from My_Indicators.volume_analyzer import VolumeAnomalyDetector
                _vd_s2 = VolumeAnomalyDetector()
                if 'volume' in df_d1.columns and len(df_d1) > 25:
                    _sp2 = _vd_s2.detect_spikes(df_d1['volume'])
                    _vol_sp2 = bool(_sp2['spikes'].iloc[-1])
            except:
                pass
            _sec_trend = _sector_result.get('sector_trend') if _sector_result else None
            _rel_str = _sector_result.get('relative_strength', 1.0) if _sector_result else 1.0
            _trin_val = _trin['trin'] if _trin and _trin['trin'] > 0 else None

            # Проверка: если HI2 нет → вердикт не выносим
            if _hi2_val is None:
                _stock_verdict = {
                    'decision': 'WAIT',
                    'crisis_mode': False,
                    'combo_signal': '⏳',
                    'score': 0,
                    'confidence': 'нет данных HI2',
                    'signals': {'1D': {'signal': '—', 'score': 0}, '4H': {'signal': '—', 'score': 0}, '1H': {'signal': '—', 'score': 0}},
                }
            else:
                _stock_verdict = get_stock_scanner_verdict(
                df_d1.copy(), _df_4h.copy() if _df_4h is not None else None, _df_1h.copy() if _df_1h is not None else None,
                _hi2_val, _garch_vol, sector_trend=_sector_trend,
                chop_val=_chop_val, adx_val=_adx_val, atr_pct=_atr_pct, relative_strength=_rel_str,
                volume_spike=_vol_sp2, trin_value=_trin_val
            )
            
            _rel_str = _sector_result.get('relative_strength', 1.0) if _sector_result else 1.0
            result = screen_stocks(ticker, df_d1, df_hi2, sector_trend=_sec_trend, relative_strength=_rel_str, trin_value=_trin_val)
            if result:
                # Новый порядок: важные колонки слева
                _row = {
                    'Тикер': ticker,
                    'Цена': result['close'],
                    'Вердикт': '',  # Заполним ниже
                    'Сигнал': _stock_verdict.get('combo_signal', '—'),
                    '1D': _stock_verdict['signals']['1D']['signal'],
                    '4H': _stock_verdict['signals']['4H']['signal'],
                    '1H': _stock_verdict['signals']['1H']['signal'],
                    'Режим': result['regime'],
                    'vs Сектор': _sector_signal,
                    'HI2': result.get('hi2') or '—',
                    'ATR': result['atr'],
                }
                
                # Старый скор (проверенный) + новый вердикт (информативно)
                _old_score = result['score']  # Старый скор с прогресс-баром
                _decision = _stock_verdict["decision"]
                if _stock_verdict.get("confidence") == "нет данных":
                    _dec_emoji = "⚠️"
                    _decision = "ВЕРДИКТ НЕ АКТУАЛЕН"
                else:
                    _dec_emoji = "🟢" if _decision == "LONG" else "🔴" if _decision == "SHORT" else "⚪"
                    if _stock_verdict.get("crisis_mode"):
                        _dec_emoji = "🌪️"
                        _decision += " КРИЗИС"
                _row["Вердикт"] = f"{_old_score} {_dec_emoji} {_decision}"
                _row['Вердикт'] = f"{_old_score} {_dec_emoji} {_decision}"
                
                rows.append(_row)
                # Сохраняем вердикт для блока входа/выхода
                if '_verdicts' not in st.session_state:
                    st.session_state['_verdicts'] = {}
                st.session_state['_verdicts'][ticker] = _stock_verdict
        except Exception as e:
            rows.append({"Тикер": ticker, "supertrend": "❌", "regime": str(e)[:50], "score": "—"})
    

    if rows:
        df_scr = pd.DataFrame(rows)
        
        def color_supertrend(val):
            if 'LONG' in str(val): return 'background-color: rgba(0,255,0,0.2); color: #00ff00; font-weight: bold'
            elif 'SHORT' in str(val): return 'background-color: rgba(255,0,0,0.2); color: #ff4444; font-weight: bold'
            return ''
        
        styled = df_scr.style
        st.dataframe(styled, use_container_width=True, hide_index=True)
        
        with st.expander("🔍 Как формируется вердикт и скор?"):
            st.markdown("""
**Факторы (0-100):**
| Фактор | Вес | Описание |
|--------|-----|----------|
| FutOI | 40% | Главный фильтр: позиции физиков/юриков |
| TradeStats | 30% | Шорт-скор: сила сигнала |
| Order Flow | 20% | OFI + Cumulative Delta |
| Тренд | 10% | Контекст рынка (SMA20) |
| HI2 | штраф до -15 | Концентрация позиций |

**Блокировка:** BLOCKED -> WAIT. Перекупленность/перепроданность ослабляют сигнал.

**Уровни:** 🔥95+ | ✅80+ | 👀60+ | ⏳40+ | ❌<40
            """)
        
        st.markdown("---")
        st.caption("💡 Цвета: 🟢 = благоприятно, 🟡/🟠 = умеренно, 🔴 = неблагоприятно, ⚪ = нейтрально")
        
        # График с уровнями для выбранного тикера
        with st.expander("📈 График D1 с уровнями", expanded=False):
            _sel_ticker = st.selectbox("Выберите тикер для графика", [r.get('ticker', r.get('Тикер', '')) for r in rows] if rows else [], key="stock_graph")
            if _sel_ticker:
                _cf = DATA_ROOT / "candles" / f"{_sel_ticker}_D1.parquet"
                if _cf.exists():
                    _df_g = pd.read_parquet(_cf)
                    if len(_df_g) > 0:
                        _df_g['begin'] = pd.to_datetime(_df_g['begin'])
                        _fig_g = go.Figure()
                        _fig_g.add_trace(go.Candlestick(
                            x=_df_g['begin'], open=_df_g['open'],
                            high=_df_g['high'], low=_df_g['low'],
                            close=_df_g['close'], name='D1'
                        ))
                        # Простые уровни: max/min за 20 дней
                        _h20 = _df_g['high'].tail(20).max()
                        _l20 = _df_g['low'].tail(20).min()
                        # POC из Volume Profile
                        _df_g['typical_price'] = (_df_g['high'] + _df_g['low'] + _df_g['close']) / 3
                        _vp = _df_g.groupby(_df_g['typical_price'].round(1))['volume'].sum().reset_index()
                        _vp = _vp.sort_values('volume', ascending=False)
                        _poc = _vp.iloc[0]['typical_price'] if len(_vp) > 0 else None
                        _fig_g.add_hline(y=_h20, line_dash="dash", line_color="red", annotation_text=f"Сопр: {_h20:.2f}")
                        _fig_g.add_hline(y=_l20, line_dash="dash", line_color="green", annotation_text=f"Подд: {_l20:.2f}")
                        if _poc:
                            _fig_g.add_hline(y=_poc, line_dash="dot", line_color="white", annotation_text=f"POC: {_poc:.2f}")
                        _fig_g.update_layout(height=400, template='plotly_dark', title=f'{_sel_ticker} D1')
                        st.plotly_chart(_fig_g, use_container_width=True)
                        
                        with st.expander("🔔 MegaAlerts", expanded=False):
                            _alerts = get_mega_alerts(_sel_ticker, market='eq', days=2)
                            if _alerts:
                                for _a in _alerts:
                                    _sev = "🔴" if _a["severity"] == "high" else "🟡"
                                    st.caption(f"{_a["time"]} | {_a["type"]}")
                            else:
                                st.caption("Нет алертов")
                        
                        # === УРОВНИ ВХОДА/ВЫХОДА + КАЛЬКУЛЯТОР ===
                        _sco = st.session_state.get('_verdicts', {}).get(_sel_ticker)
                        if _sco and _sco['decision'] != 'WAIT':
                            st.markdown("---")
                            st.subheader("📐 Уровни входа/выхода")
                            
                            _atr_val2 = _df_g['high'].iloc[-1] - _df_g['low'].iloc[-1] if len(_df_g) > 0 else 1
                            _h20_2 = _df_g['high'].tail(20).max()
                            _l20_2 = _df_g['low'].tail(20).min()
                            _close2 = _df_g['close'].iloc[-1]
                            
                            if _sco['decision'] == 'LONG':
                                _entry2 = _l20_2
                                _stop2 = _entry2 - _atr_val2 * 1.5
                                _target2 = _h20_2
                            else:
                                _entry2 = _h20_2
                                _stop2 = _entry2 + _atr_val2 * 1.5
                                _target2 = _l20_2
                            
                            col_e2, col_s2, col_t2 = st.columns(3)
                            with col_e2: st.metric("Вход", f"{_entry2:.2f}")
                            with col_s2: st.metric("Стоп-лосс", f"{_stop2:.2f}", delta=f"{abs(_entry2 - _stop2):.2f}")
                            with col_t2:
                                _pot2 = abs(_target2 - _entry2) / _entry2 * 100 if _entry2 > 0 else 0
                                st.metric("Цель", f"{_target2:.2f}", delta=f"+{_pot2:.1f}%" if _pot2 > 0 else None)
                            
                            _risk_rub2 = _deposit * _risk_pct / 100
                            _lot2 = 10  # Для акций лот = 10
                            _risk_per_lot2 = abs(_entry2 - _stop2) * _lot2
                            if _risk_per_lot2 > 0:
                                _pos2 = int(_risk_rub2 / _risk_per_lot2)
                                if _pos2 > 0:
                                    st.success(f"💰 Позиция: **{_pos2}** лотов (риск {_risk_rub2:,.0f} ₽ = {_risk_pct}% от {_deposit:,.0f} ₽)".replace(",", " "))
    else:
        st.error("Нет данных для скрининга")

elif page == "🔧 Техинфо":
    st.title("🔧 Техническая информация")
    st.caption("Детальные данные и инструменты")
    
    tab1, tab2, tab3 = st.tabs(["🕯️ Super Candles", "💰 Funding", "🕯️ Super Candles H4"])
    
    with tab1:
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
                with st.expander("📋 Последние записи (15)", expanded=False):
                    st.subheader("Последние записи")
                st.dataframe(df_ticker.tail(10), use_container_width=True, hide_index=True)

    with tab2:
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

    with tab3:
        st.title("🕯️ Super Candles H4")
        h4_path = DATA_ROOT / "supercandles_h4"
        if h4_path.exists():
            files = list(h4_path.glob("*.parquet"))
            if files:
                st.success(f"Найдено {len(files)} файлов H4")
                files.sort()
                sample_file = files[-1]
                df = pd.read_parquet(sample_file)
                st.subheader(f"Файл: {sample_file.name}")
                st.dataframe(df.tail(10), use_container_width=True)
            else:
                st.warning("Файлы H4 не найдены")
        else:
            st.error(f"Папка {h4_path} не существует")
