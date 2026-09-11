"""HMM на дневных данных GLDRUBF (из CSV)"""
import sys
from pathlib import Path
import polars as pl
import numpy as np

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from FinLabPy.My_Indicators.hmm_regime import MarketRegimeHMM

print("=" * 60)
print("HMM REGIME: GLDRUBF D1 (дневные данные)")
print("=" * 60)

# Загружаем дневные данные
df = pl.read_csv("E:/Python/Data_Qwick_Test/GLDRUBF_D1_daily.csv", try_parse_dates=True)
# Переименовываем date -> datetime для совместимости
df = df.rename({'date': 'datetime'})

print(f"Данные: {len(df)} дней")
print(f"Диапазон: {df['datetime'].min()} - {df['datetime'].max()}")
print(f"Цена: {df['close'].min():.0f} - {df['close'].max():.0f}")

for n in [3, 4]:
    print(f"\n{'='*40}")
    print(f"HMM с {n} режимами")
    print('='*40)
    
    hmm = MarketRegimeHMM(n_regimes=n)
    features = hmm.prepare_features(df)
    hmm.fit(features)
    
    states = hmm.predict(features)
    
    # Статистика по годам
    years = sorted(set(d.year for d in df['datetime'].to_list()))
    for year in years:
        mask = np.array([d.year == year for d in df['datetime'].to_list()])
        ys = states[mask]
        if len(ys) > 0:
            unique, counts = np.unique(ys, return_counts=True)
            print(f"\n{year}:")
            for u, c in zip(unique, counts):
                pct = c / len(ys) * 100
                bar = '|' * int(pct)
                print(f"  {hmm.regime_names[u]:12s}: {c:3d} дн ({pct:5.1f}%) {bar}")
    
    # Текущий режим
    rid, name, conf, probs = hmm.get_current_regime(features)
    print(f"\nТекущий: {name} (уверенность {conf:.1%})")
    print(f"Вероятности: {{{', '.join(f'{k}: {v:.1%}' for k,v in zip(hmm.regime_names, probs))}}}")

print("\nГотово!")
