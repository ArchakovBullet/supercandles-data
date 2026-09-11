"""
Расчёт технических признаков для HMM через TA-Lib.
"""
import polars as pl


def add_technical_features(df: pl.DataFrame) -> pl.DataFrame:
    """
    Добавляет 10+ технических признаков к дневным данным.
    
    Требует колонки: date, open, high, low, close, volume
    
    Возвращает тот же DataFrame с новыми колонками:
        returns, volatility, volume_ratio, trend_strength,
        price_vs_sma20, price_vs_sma50, rsi, macd_hist,
        bb_position, future_returns_1d
    """
    import talib
    import numpy as np
    
    # Конвертируем в numpy для TA-Lib
    open_arr = df['open'].to_numpy()
    high_arr = df['high'].to_numpy()
    low_arr = df['low'].to_numpy()
    close_arr = df['close'].to_numpy()
    volume_arr = df['volume'].to_numpy().astype(float)
    
    # 1. Дневная доходность
    returns = np.diff(close_arr, prepend=np.nan) / np.roll(close_arr, 1)
    returns[0] = np.nan
    
    # 2. Волатильность (ATR / close)
    atr = talib.ATR(high_arr, low_arr, close_arr, timeperiod=14)
    volatility = atr / close_arr
    
    # 3. Относительный объём
    sma_volume = talib.SMA(volume_arr, timeperiod=20)
    volume_ratio = volume_arr / sma_volume
    
    # 4. Сила тренда (ADX)
    adx = talib.ADX(high_arr, low_arr, close_arr, timeperiod=14)
    
    # 5. Цена vs SMA20
    sma20 = talib.SMA(close_arr, timeperiod=20)
    price_vs_sma20 = close_arr / sma20
    
    # 6. Цена vs SMA50
    sma50 = talib.SMA(close_arr, timeperiod=50)
    price_vs_sma50 = close_arr / sma50
    
    # 7. RSI
    rsi = talib.RSI(close_arr, timeperiod=14)
    
    # 8. MACD гистограмма
    macd, macd_signal, macd_hist = talib.MACD(close_arr, fastperiod=12, slowperiod=26, signalperiod=9)
    
    # 9. Bollinger Bands позиция
    bb_upper, bb_middle, bb_lower = talib.BBANDS(close_arr, timeperiod=20, nbdevup=2, nbdevdn=2)
    bb_range = bb_upper - bb_lower
    bb_position = (close_arr - bb_lower) / np.where(bb_range > 0, bb_range, np.nan)
    
    # 10. Будущая доходность (таргет)
    future_returns = np.roll(returns, -1)
    future_returns[-1] = np.nan
    
    # Добавляем в DataFrame
    df = df.with_columns([
        pl.Series('returns', returns),
        pl.Series('volatility', volatility),
        pl.Series('volume_ratio', volume_ratio),
        pl.Series('trend_strength', adx),
        pl.Series('price_vs_sma20', price_vs_sma20),
        pl.Series('price_vs_sma50', price_vs_sma50),
        pl.Series('rsi', rsi),
        pl.Series('macd_hist', macd_hist),
        pl.Series('bb_position', bb_position),
        pl.Series('future_returns_1d', future_returns),
    ])
    
    return df


# ============ ТЕСТ ============
if __name__ == '__main__':
    import os
    import sys
    from pathlib import Path
    
    project_root = Path('.').absolute()
    sys.path.insert(0, str(project_root))
    
    from MOEXPy.MOEXPy import MOEXPy
    from FinLabPy.DataCollectors.m10_to_d1_converter import M10ToD1Converter
    
    api = MOEXPy(token=os.getenv('MOEX_TOKEN'))
    converter = M10ToD1Converter(api)
    
    print('Загрузка данных SBER...')
    df = converter.convert('TQBR', 'SBER', days=90, include_trades=False)
    
    print('Расчёт технических признаков...')
    df = add_technical_features(df)
    
    print(f'\n{"="*60}')
    print(f'Результат: {df.shape[0]} дней, {df.shape[1]} колонок')
    print(f'Колонки: {df.columns}')
    print(f'\nПоследние 5 дней:')
    print(df.tail(5))
