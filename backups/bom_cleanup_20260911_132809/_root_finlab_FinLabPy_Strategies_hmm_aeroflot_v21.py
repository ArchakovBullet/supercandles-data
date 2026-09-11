"""
HMM + SuperTrend стратегия v2.1: смягчённый фильтр (ИЛИ).
Вход: HMM UP ИЛИ SuperTrend UP
Выход: HMM NOT UP И SuperTrend DOWN
ATR-стоп 2× + трейлинг-безубыток 3%
"""
import os, sys, numpy as np, polars as pl, matplotlib.pyplot as plt
from pathlib import Path
from hmmlearn import hmm as hmmlearn_hmm
import talib

project_root = Path(__file__).parent.parent.parent if '__file__' in dir() else Path('.').absolute()
sys.path.insert(0, str(project_root))

from FinLabPy.DataCollectors.osengine_loader import OsEngineLoader
from FinLabPy.My_Indicators.technical_features import add_technical_features
from FinLabPy.Utils import setup_logger

logger = setup_logger('hmm_v21')


def compute_super_trend(high, low, close, period=10, multiplier=3.0):
    atr = talib.ATR(high, low, close, timeperiod=period)
    hl_avg = (high + low) / 2
    upper, lower = hl_avg + multiplier*atr, hl_avg - multiplier*atr
    n = len(close); st_line, st_dir = np.zeros(n), np.zeros(n)
    for i in range(1, n):
        upper[i] = upper[i] if upper[i]<upper[i-1] or close[i-1]>upper[i-1] else upper[i-1]
        lower[i] = lower[i] if lower[i]>lower[i-1] or close[i-1]<lower[i-1] else lower[i-1]
        if close[i] > upper[i-1]: st_dir[i]=1; st_line[i]=lower[i]
        elif close[i] < lower[i-1]: st_dir[i]=-1; st_line[i]=upper[i]
        else: st_dir[i]=st_dir[i-1]; st_line[i]=lower[i] if st_dir[i]==1 else upper[i]
    return st_line, st_dir


def prepare_features(df):
    df = add_technical_features(df)
    close = df['close'].to_numpy().astype(np.float64)
    high = df['high'].to_numpy().astype(np.float64)
    low = df['low'].to_numpy().astype(np.float64)
    dates = df['date'].to_list()
    st_line, st_dir = compute_super_trend(high, low, close)
    adx = talib.ADX(high, low, close, 14)
    base = ['returns','volatility','volume_ratio','trend_strength',
            'price_vs_sma20','price_vs_sma50','rsi','macd_hist','bb_position']
    X = np.column_stack([df.select(base).to_numpy().astype(np.float64), st_dir, (adx>25).astype(float)])
    y = df['future_returns_1d'].to_numpy().astype(np.float64)
    m = ~np.isnan(X).any(1) & ~np.isinf(X).any(1) & ~np.isnan(y) & ~np.isinf(y)
    return X[m], y[m], close[m], high[m], low[m], [d for i,d in enumerate(dates) if m[i]], st_line[m], st_dir[m]


def backtest(model, X, close, high, low, up_state, st_dir, atr_mult=2.0, breakeven=3.0):
    states = model.predict(X); atr = talib.ATR(high, low, close, 14)
    n = len(close); pos, entry, bar, stop_lvl = 0,0,0,0
    trades, eq = [], np.ones(n); peak, dd = 1.0,0.0; sig, stp = 0,0
    for i in range(1, n):
        eq[i] = eq[i-1]
        if pos:
            ret = (close[i]-entry)/entry*100
            if ret >= breakeven: stop_lvl = max(stop_lvl, entry)
            if low[i] <= stop_lvl:
                r = (stop_lvl-entry)/entry; eq[i]=eq[i-1]*(1+r); pos=0; stp+=1
                trades.append({'t':'STOP','i':i,'p':stop_lvl,'r':r,'b':i-bar}); continue
        h_up = states[i]==up_state; s_up = st_dir[i]==1
        if (h_up or s_up) and not pos:
            pos=1; entry=close[i]; bar=i; stop_lvl=entry-atr_mult*atr[i]
            trades.append({'t':'BUY','i':i,'p':close[i]})
        elif (not h_up) and st_dir[i]==-1 and pos:
            r = (close[i]-entry)/entry; eq[i]=eq[i-1]*(1+r); pos=0; sig+=1
            trades.append({'t':'SELL','i':i,'p':close[i],'r':r,'b':i-bar})
        if eq[i]>peak: peak=eq[i]
        if (eq[i]-peak)/peak < dd: dd = (eq[i]-peak)/peak
    if pos:
        r = (close[-1]-entry)/entry; eq[-1]=eq[-2]*(1+r)
        trades.append({'t':'END','i':n-1,'p':close[-1],'r':r,'b':n-1-bar})
    comp = [t for t in trades if 'r' in t]; wins = [t for t in comp if t['r']>0]
    return {
        'total':float((eq[-1]-1)*100), 'bh':float((close[-1]-close[0])/close[0]*100),
        'delta':float((eq[-1]-1)*100 - (close[-1]-close[0])/close[0]*100),
        'deals':len(comp), 'win':len(wins)/max(len(comp),1)*100, 'dd':float(dd*100),
        'sig':sig, 'stp':stp, 'bars':float(np.mean([t['b'] for t in comp])) if comp else 0,
        'avg_r':float(np.mean([t['r'] for t in comp])*100) if comp else 0,
        'eq':eq, 'st':states, 'cl':close, 'tr':trades
    }


def plot_results(r, ticker):
    st, cl, eq, tr = r['st'], r['cl'], r['eq'], r['tr']
    n=len(cl); x=np.arange(n)
    fig,(ax1,ax2)=plt.subplots(2,1,figsize=(18,10),gridspec_kw={'height_ratios':[3,1]})
    cs = ['#FFE0E0','#E0FFE0','#E0E0FF','#FFFFE0']
    for s in sorted(set(st)):
        m=st==s; segs=[]; start=None
        for i in range(n):
            if m[i] and start is None: start=i
            elif not m[i] and start is not None: segs.append((start,i-1)); start=None
        if start is not None: segs.append((start,n-1))
        for a,b in segs:
            if b>a: ax1.axvspan(a,b,alpha=0.12,color=cs[s%4])
    ax1.plot(x,cl,'k-',lw=1,label=ticker)
    buys=[t for t in tr if t['t']=='BUY']; ex=[t for t in tr if 'r' in t]
    if buys: ax1.scatter([t['i'] for t in buys],[t['p'] for t in buys],
                         c='lime',marker='^',s=150,zorder=10,edgecolors='green',lw=2)
    if ex: ax1.scatter([t['i'] for t in ex],[t['p'] for t in ex],
                       c='red',marker='v',s=100,zorder=10,edgecolors='darkred',lw=1.5)
    ax1.set_title(f'HMM+SuperTrend (ИЛИ): {ticker} | ATR-стоп 2× | Безубыток 3%',fontsize=13,fontweight='bold')
    ax1.legend(loc='upper left'); ax1.grid(True,alpha=0.3)
    ax2.plot(x,eq,'g-',lw=1.5,label=f'Стратегия: {r["total"]:.1f}%')
    bh=(cl-cl[0])/cl[0]+1; ax2.plot(x,bh,'k--',lw=1,alpha=0.5,label=f'B&H: {r["bh"]:.1f}%')
    ax2.axhline(1.0,color='gray',ls=':',alpha=0.5)
    ax2.set_xlabel('Дни'); ax2.set_ylabel('Капитал (×)'); ax2.legend(loc='upper left'); ax2.grid(True,alpha=0.3)
    t=(f'Δ={r["delta"]:.1f}% | Сделок: {r["deals"]} | Win: {r["win"]:.0f}% | DD: {r["dd"]:.1f}%\n'
       f'Сигнал: {r["sig"]} | Стоп: {r["stp"]} | Срок: {r["bars"]:.0f}д | Доход/сд: {r["avg_r"]:.1f}%')
    ax2.text(0.02,0.98,t,transform=ax2.transAxes,fontsize=10,va='top',
            fontfamily='monospace',bbox=dict(boxstyle='round',facecolor='lightyellow',alpha=0.9))
    plt.tight_layout(); plt.savefig(f'hmm_v21_{ticker}.png',dpi=150,bbox_inches='tight'); plt.show()


if __name__ == '__main__':
    loader=OsEngineLoader(); ticker='Аэрофлот'
    logger.info(f'Загрузка: {ticker}')
    df=loader.load(ticker); daily=loader.to_daily(df)
    X,y,close,high,low,dates,st_line,st_dir = prepare_features(daily)
    logger.info(f'Данные: {len(X)}д, {dates[0]} — {dates[-1]}, признаков: {X.shape[1]}')
    
    split=int(len(X)*0.7)
    X_tr,X_te = X[:split],X[split:]
    close_tr,close_te = close[:split],close[split:]
    high_te,low_te = high[split:],low[split:]
    st_dir_te = st_dir[split:]; dates_te = dates[split:]
    
    logger.info(f'Train: {len(X_tr)}д | Test: {len(X_te)}д')
    
    model = hmmlearn_hmm.GaussianHMM(n_components=4,covariance_type='full',n_iter=1000,random_state=42,tol=1e-4)
    model.fit(X_tr)
    st_tr = model.predict(X_tr)
    
    rr={}
    for s in range(4):
        m=st_tr==s
        if m.sum()>5: rr[s]=float(np.mean(np.diff(close_tr[m])/(close_tr[m][:-1]+1e-10)))
    up_state=max(rr,key=rr.get)
    for s,r in sorted(rr.items(),key=lambda x:x[1],reverse=True):
        logger.info(f'  State {s}: avg={r:.4%}, дней={(st_tr==s).sum()}')
    logger.info(f'UP: State {up_state}')
    
    results = backtest(model, X_te, close_te, high_te, low_te, up_state, st_dir_te)
    logger.info(f'\nДоход: {results["total"]:.1f}% | B&H: {results["bh"]:.1f}% | Δ: {results["delta"]:.1f}%')
    logger.info(f'Сделок: {results["deals"]} | Win: {results["win"]:.0f}% | DD: {results["dd"]:.1f}%')
    logger.info(f'Сигнал: {results["sig"]} | Стоп: {results["stp"]} | Срок: {results["bars"]:.0f}д')
    
    plot_results(results, ticker)
