"""
Бэктест вердиктов v3 — детальный анализ с бенчмарками B&H и LQDT.
Графики: win-rate по времени, распределение доходностей, сравнение с бенчмарком.
"""
import sys
sys.path.insert(0, '/root/finlab/FinLabPy')

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
import json
import plotly.graph_objects as go
from plotly.subplots import make_subplots

DATA_ROOT = Path('/root/finlab/data')
OUTPUT_DIR = DATA_ROOT / 'backtest_v3'
OUTPUT_DIR.mkdir(exist_ok=True)

TICKERS = ['CNYRUBF', 'EURRUBF', 'GAZPF', 'GLDRUBF', 'IMOEXF', 'SBERF', 'USDRUBF',
           'BR', 'GD', 'MX', 'RI', 'SI', 'SV', 'VI', 'W4']

HORIZON = 5  # дней

def get_signal(futoi_df, current_date):
    """Упрощённый сигнал: LONG если fiz_buy > 60 и растёт, SHORT если < 40 и падает."""
    fiz = futoi_df[futoi_df['clgroup'] == 'FIZ']
    if len(fiz) < 3:
        return None, None
    
    # Берём данные до current_date
    fiz['tradedate'] = pd.to_datetime(fiz['tradedate']).dt.date
    fiz_window = fiz[fiz['tradedate'] <= current_date]
    if len(fiz_window) < 2:
        return None, None
    
    last = fiz_window.iloc[-1]
    prev = fiz_window.iloc[-2]
    
    fiz_buy = last['pos_long_num'] / (last['pos_long_num'] + last['pos_short_num'] + 1) * 100
    fiz_buy_prev = prev['pos_long_num'] / (prev['pos_long_num'] + prev['pos_short_num'] + 1) * 100
    delta = fiz_buy - fiz_buy_prev
    
    if fiz_buy > 60 and delta > 0.1:
        return 'LONG', fiz_buy
    elif fiz_buy < 40 and delta < -0.1:
        return 'SHORT', fiz_buy
    return 'NEUTRAL', fiz_buy

def get_session_liquidity(date):
    """LQDT-фильтр: только основная сессия."""
    weekday = pd.Timestamp(date).dayofweek
    if weekday >= 5:  # выходные
        return False
    return True  # упрощённо: все будние дни ликвидны

def backtest_ticker(ticker):
    """Детальный бэктест для одного тикера."""
    futoi_file = DATA_ROOT / 'futoi' / f'{ticker}_futoi.parquet'
    d1_file = DATA_ROOT / 'candles' / f'{ticker}_D1.parquet'
    
    if not futoi_file.exists() or not d1_file.exists():
        return None
    
    df_futoi = pd.read_parquet(futoi_file)
    df_d1 = pd.read_parquet(d1_file)
    
    if len(df_d1) < 30:
        return None
    
    df_d1['date'] = pd.to_datetime(df_d1['begin']).dt.date
    
    signals = []
    lqdt_signals = []
    bh_returns = []
    
    for i in range(20, len(df_d1) - HORIZON):
        current_date = df_d1['date'].iloc[i]
        current_price = df_d1['close'].iloc[i]
        future_price = df_d1['close'].iloc[i + HORIZON]
        ret = (future_price - current_price) / current_price * 100
        
        # B&H
        bh_returns.append(ret)
        
        # LQDT-фильтр
        if get_session_liquidity(current_date):
            lqdt_signals.append(ret)
        
        # Наш сигнал
        signal_type, fiz_buy = get_signal(df_futoi, current_date)
        if signal_type in ['LONG', 'SHORT']:
            signal_ret = ret if signal_type == 'LONG' else -ret
            signals.append({
                'date': current_date,
                'signal': signal_type,
                'fiz_buy': fiz_buy,
                'return': round(signal_ret, 2),
                'win': signal_ret > 0
            })
    
    return {
        'ticker': ticker,
        'signals': signals,
        'lqdt_returns': lqdt_signals,
        'bh_returns': bh_returns
    }

def make_charts(ticker, data):
    """Создаёт графики для тикера."""
    if not data['signals']:
        return None
    
    df = pd.DataFrame(data['signals'])
    
    # 1. Win-rate по времени (скользящее окно)
    df = df.sort_values('date')
    df['cum_win_rate'] = df['win'].expanding().mean() * 100
    df['rolling_win_rate'] = df['win'].rolling(10, min_periods=3).mean() * 100
    
    # 2. Распределение доходностей
    fig = make_subplots(rows=2, cols=2,
        subplot_titles=('Win-rate по времени', 'Распределение доходностей',
                       'Сравнение с бенчмарками', 'Доходность сигналов'))
    
    # Win-rate
    fig.add_trace(go.Scatter(y=df['cum_win_rate'], mode='lines', name='Кумулятивный win-rate',
                             line=dict(color='#00ff00')), row=1, col=1)
    fig.add_trace(go.Scatter(y=df['rolling_win_rate'], mode='lines', name='Скользящий (10)',
                             line=dict(color='#ffaa00')), row=1, col=1)
    fig.add_hline(y=50, line_dash="dash", line_color="red", row=1, col=1)
    
    # Распределение
    fig.add_trace(go.Histogram(x=df['return'], nbinsx=20, name='Доходности',
                               marker_color='#00BFFF'), row=1, col=2)
    
    # Сравнение с бенчмарками
    bh_avg = np.mean(data['bh_returns']) if data['bh_returns'] else 0
    lqdt_avg = np.mean(data['lqdt_returns']) if data['lqdt_returns'] else 0
    signal_avg = df['return'].mean()
    
    benchmarks = ['B&H', 'LQDT', 'Наш сигнал']
    values = [bh_avg, lqdt_avg, signal_avg]
    colors = ['#888', '#ffaa00', '#00ff00']
    fig.add_trace(go.Bar(x=benchmarks, y=values, marker_color=colors, name='Средняя доходность'),
                  row=2, col=1)
    
    # Доходность сигналов
    fig.add_trace(go.Scatter(y=df['return'].cumsum(), mode='lines', name='Кумулятивная доходность',
                             line=dict(color='#00ff00')), row=2, col=2)
    
    fig.update_layout(height=800, template='plotly_dark', title=f'{ticker} — Бэктест вердиктов')
    fig.update_xaxes(title_text="Дни", row=2, col=2)
    fig.update_yaxes(title_text="Win-rate %", row=1, col=1)
    fig.update_yaxes(title_text="Доходность %", row=2, col=2)
    
    return fig

def main():
    print("=" * 60)
    print("БЭКТЕСТ ВЕРДИКТОВ v3 — детальный анализ с бенчмарками")
    print(f"Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    all_results = {}
    
    for ticker in TICKERS:
        data = backtest_ticker(ticker)
        if data and data['signals']:
            df = pd.DataFrame(data['signals'])
            win_rate = df['win'].mean() * 100
            avg_ret = df['return'].mean()
            sharpe = avg_ret / df['return'].std() if df['return'].std() > 0 else 0
            
            bh_avg = np.mean(data['bh_returns']) if data['bh_returns'] else 0
            lqdt_avg = np.mean(data['lqdt_returns']) if data['lqdt_returns'] else 0
            
            vs_bh = avg_ret - bh_avg
            vs_lqdt = avg_ret - lqdt_avg
            
            print(f"\n📊 {ticker}: {len(df)} сигналов, win={win_rate:.0f}%, avg={avg_ret:+.2f}%, Sharpe={sharpe:.2f}")
            print(f"   vs B&H: {vs_bh:+.2f}% | vs LQDT: {vs_lqdt:+.2f}%")
            
            all_results[ticker] = {
                'n_signals': len(df),
                'win_rate': round(win_rate, 1),
                'avg_return': round(avg_ret, 2),
                'sharpe': round(sharpe, 2),
                'vs_bh': round(vs_bh, 2),
                'vs_lqdt': round(vs_lqdt, 2)
            }
            
            # График
            fig = make_charts(ticker, data)
            if fig:
                fig.write_html(OUTPUT_DIR / f'{ticker}_backtest.html')
                print(f"   График сохранён: {ticker}_backtest.html")
    
    # Сохраняем сводку
    with open(OUTPUT_DIR / 'summary.json', 'w') as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Результаты сохранены в {OUTPUT_DIR}")

if __name__ == '__main__':
    main()
