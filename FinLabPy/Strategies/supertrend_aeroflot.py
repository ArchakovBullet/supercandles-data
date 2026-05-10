"""
SuperTrend стратегия для Аэрофлота (без HMM).
Вход: SuperTrend UP (зелёный)
Выход: SuperTrend DOWN (красный)
ATR-стоп 2× + трейлинг-безубыток 3%
"""
import os, sys, numpy as np, polars as pl, matplotlib.pyplot as plt
from pathlib import Path
import talib

project_root = Path(__file__).parent.parent.parent if '__file__' in dir() else Path('.').absolute()
sys.path.insert(0, str(project_root))

from FinLabPy.DataCollectors.osengine_loader import OsEngineLoader
from FinLabPy.Utils import setup_logger

logger = setup_logger('supertrend')


def super_trend(high, low, close, period=10, multiplier=3.0):
    atr = talib.ATR(high, low, close, period)
    hl = (high+low)/2
    up, lo = hl+multiplier*atr, hl-multiplier*atr
    n=len(close); st=np.zeros(n); sd=np.zeros(n)
    for i in range(1,n):
        up[i]=up[i] if up[i]<up[i-1] or close[i-1]>up[i-1] else up[i-1]
        lo[i]=lo[i] if lo[i]>lo[i-1] or close[i-1]<lo[i-1] else lo[i-1]
        if close[i]>up[i-1]: sd[i]=1; st[i]=lo[i]
        elif close[i]<lo[i-1]: sd[i]=-1; st[i]=up[i]
        else: sd[i]=sd[i-1]; st[i]=lo[i] if sd[i]==1 else up[i]
    return st, sd


def backtest_st(close, high, low, st_dir, atr_mult=2.0, breakeven=3.0):
    atr = talib.ATR(high, low, close, 14)
    n=len(close); pos,entry,bar,stop_lvl=0,0,0,0
    trades,eq=[],np.ones(n); peak,dd=1.0,0.0
    for i in range(1,n):
        eq[i]=eq[i-1]
        if pos:
            ret=(close[i]-entry)/entry*100
            if ret>=breakeven: stop_lvl=max(stop_lvl,entry)
            if low[i]<=stop_lvl:
                r=(stop_lvl-entry)/entry; eq[i]=eq[i-1]*(1+r); pos=0
                trades.append({'t':'STOP','i':i,'p':stop_lvl,'r':r,'b':i-bar}); continue
        if st_dir[i]==1 and not pos:
            pos=1; entry=close[i]; bar=i; stop_lvl=entry-atr_mult*atr[i]
            trades.append({'t':'BUY','i':i,'p':close[i]})
        elif st_dir[i]==-1 and pos:
            r=(close[i]-entry)/entry; eq[i]=eq[i-1]*(1+r); pos=0
            trades.append({'t':'SELL','i':i,'p':close[i],'r':r,'b':i-bar})
        if eq[i]>peak: peak=eq[i]
        if (eq[i]-peak)/peak<dd: dd=(eq[i]-peak)/peak
    if pos:
        r=(close[-1]-entry)/entry; eq[-1]=eq[-2]*(1+r)
        trades.append({'t':'END','i':n-1,'p':close[-1],'r':r,'b':n-1-bar})
    comp=[t for t in trades if 'r' in t]; wins=[t for t in comp if t['r']>0]
    return {
        'total':float((eq[-1]-1)*100),'bh':float((close[-1]-close[0])/close[0]*100),
        'delta':float((eq[-1]-1)*100-(close[-1]-close[0])/close[0]*100),
        'deals':len(comp),'win':len(wins)/max(len(comp),1)*100,'dd':float(dd*100),
        'eq':eq,'tr':trades,'st_dir':st_dir
    }


def plot_st(r, ticker, close, st_line, st_dir):
    eq,tr=r['eq'],r['tr']; n=len(close); x=np.arange(n)
    fig,(ax1,ax2)=plt.subplots(2,1,figsize=(18,10),gridspec_kw={'height_ratios':[3,1]})
    
    # Фон SuperTrend
    for i in range(1,n):
        c='#E0FFE0' if st_dir[i]==1 else '#FFE0E0'
        ax1.axvspan(i-1,i,alpha=0.15,color=c)
    
    ax1.plot(x,close,'k-',lw=1,label=ticker)
    ax1.plot(x,st_line,'b--',lw=1,alpha=0.8,label='SuperTrend')
    
    buys=[t for t in tr if t['t']=='BUY']; ex=[t for t in tr if 'r' in t]
    if buys: ax1.scatter([t['i'] for t in buys],[t['p'] for t in buys],
                         c='lime',marker='^',s=150,zorder=10,edgecolors='green',lw=2)
    if ex: ax1.scatter([t['i'] for t in ex],[t['p'] for t in ex],
                       c='red',marker='v',s=100,zorder=10,edgecolors='darkred',lw=1.5)
    
    ax1.set_title(f'SuperTrend: {ticker} | ATR-стоп 2× | Безубыток 3%',fontsize=13,fontweight='bold')
    ax1.legend(loc='upper left'); ax1.grid(True,alpha=0.3)
    
    ax2.plot(x,eq,'g-',lw=1.5,label=f'ST: {r["total"]:.1f}%')
    bh=(close-close[0])/close[0]+1
    ax2.plot(x,bh,'k--',lw=1,alpha=0.5,label=f'B&H: {r["bh"]:.1f}%')
    ax2.axhline(1.0,color='gray',ls=':',alpha=0.5)
    ax2.set_xlabel('Дни'); ax2.set_ylabel('Капитал (×)'); ax2.legend(); ax2.grid(True,alpha=0.3)
    
    t=f'Δ={r["delta"]:.1f}% | Сделок: {r["deals"]} | Win: {r["win"]:.0f}% | DD: {r["dd"]:.1f}%'
    ax2.text(0.02,0.98,t,transform=ax2.transAxes,fontsize=11,va='top',
            fontfamily='monospace',bbox=dict(boxstyle='round',facecolor='lightyellow',alpha=0.9))
    
    plt.tight_layout(); plt.savefig(f'st_{ticker}.png',dpi=150,bbox_inches='tight'); plt.show()


if __name__=='__main__':
    loader=OsEngineLoader(); ticker='Аэрофлот'
    df=loader.load(ticker); daily=loader.to_daily(df)
    close=daily['close'].to_numpy().astype(np.float64)
    high=daily['high'].to_numpy().astype(np.float64)
    low=daily['low'].to_numpy().astype(np.float64)
    dates=daily['date'].to_list()
    
    # Берём последние 30% как "тест"
    split=int(len(close)*0.7)
    close_te,high_te,low_te=close[split:],high[split:],low[split:]
    
    st_line, st_dir = super_trend(high_te, low_te, close_te)
    results = backtest_st(close_te, high_te, low_te, st_dir)
    
    logger.info(f'SuperTrend {ticker}: {results["total"]:.1f}% vs B&H {results["bh"]:.1f}% | Δ={results["delta"]:.1f}%')
    logger.info(f'Сделок: {results["deals"]} | Win: {results["win"]:.0f}% | DD: {results["dd"]:.1f}%')
    
    plot_st(results, ticker, close_te, st_line, st_dir)
