"""
Скринер акций: SuperTrend + ADX + Choppiness Index
"""

import pandas as pd
import numpy as np


def calculate_supertrend(df, period=10, multiplier=3):
    """Рассчитывает SuperTrend. Возвращает: trend (1=LONG, -1=SHORT), supertrend (линия)"""
    if df is None or len(df) < period:
        return pd.Series([0]*len(df) if df is not None else []), pd.Series([])
    
    high = df['high']
    low = df['low']
    close = df['close']
    
    # ATR
    tr = pd.DataFrame({
        'h_l': high - low,
        'h_c': abs(high - close.shift()),
        'l_c': abs(low - close.shift())
    }).max(axis=1)
    atr = tr.rolling(period).mean()
    
    # Базовая линия
    hl_avg = (high + low) / 2
    
    # Верхняя и нижняя полосы
    upper_band = hl_avg + multiplier * atr
    lower_band = hl_avg - multiplier * atr
    
    # SuperTrend
    supertrend = pd.Series(0.0, index=df.index)
    trend = pd.Series(0, index=df.index)
    
    for i in range(period, len(df)):
        if close.iloc[i] > supertrend.iloc[i-1] if i > period else 0:
            trend.iloc[i] = 1  # LONG
            supertrend.iloc[i] = max(lower_band.iloc[i], supertrend.iloc[i-1] if i > period and trend.iloc[i-1] == 1 else lower_band.iloc[i])
        else:
            trend.iloc[i] = -1  # SHORT
            supertrend.iloc[i] = min(upper_band.iloc[i], supertrend.iloc[i-1] if i > period and trend.iloc[i-1] == -1 else upper_band.iloc[i])
    
    return trend, supertrend


def calculate_adx(df, period=14):
    """Рассчитывает ADX (Average Directional Index)"""
    if df is None or len(df) < period * 2:
        return pd.Series([0]*len(df) if df is not None else [])
    
    high = df['high']
    low = df['low']
    close = df['close']
    
    # True Range
    tr = pd.DataFrame({
        'h_l': high - low,
        'h_c': abs(high - close.shift()),
        'l_c': abs(low - close.shift())
    }).max(axis=1)
    
    # Directional Movement
    up_move = high - high.shift()
    down_move = low.shift() - low
    
    plus_dm = pd.Series(0.0, index=df.index)
    minus_dm = pd.Series(0.0, index=df.index)
    
    plus_dm[(up_move > down_move) & (up_move > 0)] = up_move
    minus_dm[(down_move > up_move) & (down_move > 0)] = down_move
    
    # Smoothing
    atr = tr.rolling(period).mean()
    plus_di = 100 * plus_dm.rolling(period).mean() / atr
    minus_di = 100 * minus_dm.rolling(period).mean() / atr
    
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
    adx = dx.rolling(period).mean()
    
    return adx.fillna(0)


def calculate_choppiness(df, period=14):
    """Рассчитывает Choppiness Index (0-100). <38 = тренд, >62 = флэт"""
    if df is None or len(df) < period:
        return pd.Series([50]*len(df) if df is not None else [])
    
    high = df['high']
    low = df['low']
    close = df['close']
    
    # True Range сумма
    tr = pd.DataFrame({
        'h_l': high - low,
        'h_c': abs(high - close.shift()),
        'l_c': abs(low - close.shift())
    }).max(axis=1)
    
    atr_sum = tr.rolling(period).sum()
    
    # Диапазон
    highest_high = high.rolling(period).max()
    lowest_low = low.rolling(period).min()
    range_period = highest_high - lowest_low
    
    choppiness = 100 * np.log10(atr_sum / range_period) / np.log10(period)
    return choppiness.fillna(50)


def screen_stocks(ticker, df_d1, df_hi2=None, sector_trend=None, relative_strength=1.0, trin_value=None):
    """
    Проводит скрининг одной акции.
    Возвращает словарь с результатами.
    """
    if df_d1 is None or len(df_d1) < 30:
        return None
    
    # SuperTrend
    trend, supertrend = calculate_supertrend(df_d1)
    last_trend = trend.iloc[-1] if len(trend) > 0 else 0
    st_signal = "🟢 LONG" if last_trend == 1 else "🔴 SHORT" if last_trend == -1 else "⚪ —"
    
    # ADX
    adx = calculate_adx(df_d1)
    last_adx = adx.iloc[-1] if len(adx) > 0 else 0
    
    # Choppiness
    chop = calculate_choppiness(df_d1)
    last_chop = chop.iloc[-1] if len(chop) > 0 else 50
    
    # ATR
    tr = pd.DataFrame({
        'h_l': df_d1['high'] - df_d1['low'],
        'h_c': abs(df_d1['high'] - df_d1['close'].shift()),
        'l_c': abs(df_d1['low'] - df_d1['close'].shift())
    }).max(axis=1)
    atr_val = tr.rolling(14).mean().iloc[-1]
    atr_pct = atr_val / df_d1['close'].iloc[-1] * 100 if df_d1['close'].iloc[-1] > 0 else 0
    
    # HI2
    hi2_val = None
    if df_hi2 is not None:
        hi2_agressive = df_hi2[df_hi2['metric'] == 'hhi_agressive']
        if len(hi2_agressive) > 0:
            hi2_val = hi2_agressive.sort_values('tradedate').iloc[-1]['value']
    
    # Тренд (SMA20)
    df_d1['sma20'] = df_d1['close'].rolling(20).mean()
    last_close = df_d1['close'].iloc[-1]
    sma20 = df_d1['sma20'].iloc[-1]
    if last_close < sma20 * 0.98:
        trend_text = "📉 Медвежий"
    elif last_close > sma20 * 1.02:
        trend_text = "📈 Бычий"
    else:
        trend_text = "◼ Боковик"
    
    # Режим
    if last_chop < 38 and last_adx > 25:
        regime = "🚀 Тренд"
    elif last_chop > 62 and last_adx < 20:
        regime = "🔄 Флэт"
    else:
        regime = "⚠️ Переходный"
    
    # Форматируем ADX
    if last_adx > 25:
        adx_text = f"🟢 Сильный ({last_adx:.0f})"
    elif last_adx > 20:
        adx_text = f"🟡 Средний ({last_adx:.0f})"
    else:
        adx_text = f"⚪ Слабый ({last_adx:.0f})"
    
    # Форматируем Choppiness
    if last_chop < 38:
        chop_text = f"🟢 Тренд ({last_chop:.0f})"
    elif last_chop <= 62:
        chop_text = f"🟡 Переход ({last_chop:.0f})"
    else:
        chop_text = f"🔴 Флэт ({last_chop:.0f})"
    
    # Форматируем ATR
    if atr_pct < 1.0:
        atr_text = f"⚪ Низкая ({atr_pct:.1f}%)"
    elif atr_pct <= 2.5:
        atr_text = f"🟡 Средняя ({atr_pct:.1f}%)"
    else:
        atr_text = f"🔴 Высокая ({atr_pct:.1f}%)"
    
    # Форматируем HI2
    if hi2_val is None:
        hi2_text = "—"
    elif hi2_val > 500:
        hi2_text = f"🔴 Экстр. ({hi2_val:.0f})"
    elif hi2_val > 150:
        hi2_text = f"🟠 Высокая ({hi2_val:.0f})"
    elif hi2_val > 70:
        hi2_text = f"🟡 Средняя ({hi2_val:.0f})"
    else:
        hi2_text = f"⚪ Низкая ({hi2_val:.0f})"
    
    # Режим
    regime_full = f"{regime} (ADX {last_adx:.0f}, Chop {last_chop:.0f})"
    
    # === СКОР НАДЁЖНОСТИ (0-100) ===
    score = 0
    factors = {}
    
    # Режим (35%)
    if last_chop < 38 and last_adx > 25:
        score += 35
        factors['regime'] = f"🚀 Тренд (Chop={last_chop:.0f}, ADX={last_adx:.0f}) — +35"
    elif last_chop <= 62:
        score += 15
        factors['regime'] = f"⚠️ Переходный (Chop={last_chop:.0f}) — +15"
    else:
        factors['regime'] = f"🔄 Флэт (Chop={last_chop:.0f}) — 0"
    
    # ADX (25%)
    if last_adx > 40:
        score += 25
        factors['adx'] = f"ADX={last_adx:.0f} (>40) — +25"
    elif last_adx > 25:
        score += 20
        factors['adx'] = f"ADX={last_adx:.0f} (>25) — +20"
    elif last_adx > 20:
        score += 10
        factors['adx'] = f"ADX={last_adx:.0f} (>20) — +10"
    else:
        factors['adx'] = f"ADX={last_adx:.0f} (<20) — 0"
    
    # HI2 (25%)
    if hi2_val is not None:
        if hi2_val > 500:
            score += 25
            factors['hi2'] = f"HI2={hi2_val:.0f} (>500) — +25"
        elif hi2_val > 150:
            score += 20
            factors['hi2'] = f"HI2={hi2_val:.0f} (>150) — +20"
        elif hi2_val > 70:
            score += 10
            factors['hi2'] = f"HI2={hi2_val:.0f} (>70) — +10"
        else:
            score += 5
            factors['hi2'] = f"HI2={hi2_val:.0f} (<70) — +5"
    else:
        factors['hi2'] = "HI2: нет данных — 0"
    
    # SuperTrend (15%)
    if last_trend != 0:
        score += 15
        factors['st'] = f"SuperTrend: {st_signal} — +15"
    else:
        factors['st'] = "SuperTrend: нет сигнала — 0"
    
    # === НОВЫЕ ФАКТОРЫ ===
    # Тренд SMA20 (модификатор)
    trend_mod = 0
    if trend_text == "📈 Бычий" and last_trend == 1:
        trend_mod = +5
        factors['trend'] = f"Тренд бычий + SuperTrend LONG — +5"
    elif trend_text == "📉 Медвежий" and last_trend == -1:
        trend_mod = +5
        factors['trend'] = f"Тренд медвежий + SuperTrend SHORT — +5"
    elif trend_text == "📈 Бычий" and last_trend == -1:
        trend_mod = -5
        factors['trend'] = f"Тренд бычий, но SuperTrend SHORT — противоречие (-5)"
    elif trend_text == "📉 Медвежий" and last_trend == 1:
        trend_mod = -5
        factors['trend'] = f"Тренд медвежий, но SuperTrend LONG — противоречие (-5)"
    else:
        factors['trend'] = f"Тренд {trend_text} — без влияния"
    score += trend_mod
    
    # GARCH (модификатор)
    garch_mod = 0
    try:
        from My_Indicators.garch_indicator import calculate_garch_for_ticker
        garch_result = calculate_garch_for_ticker(df_d1, ticker)
        garch_vol = garch_result.get('garch_vol', 0)
        if garch_vol > 35:
            garch_mod = -15
            factors['garch'] = f"GARCH={garch_vol:.1f}% (>35%) — блокировка (-15)"
        elif garch_vol > 25:
            garch_mod = -8
            factors['garch'] = f"GARCH={garch_vol:.1f}% (>25%) — штраф (-8)"
        elif garch_vol > 15:
            garch_mod = -2
            factors['garch'] = f"GARCH={garch_vol:.1f}% (>15%) — штраф (-2)"
        else:
            factors['garch'] = f"GARCH={garch_vol:.1f}% — норма"
    except:
        factors['garch'] = "GARCH: нет данных"
    score += garch_mod
    
    # === СЕКТОР — модификатор ===
    sector_mod = 0
    if sector_trend is not None:
        if sector_trend == 'LONG' and last_trend == 1:
            sector_mod = +10
            factors['sector'] = f"Сектор LONG — подтверждает (+10)"
        elif sector_trend == 'SHORT' and last_trend == -1:
            sector_mod = +10
            factors['sector'] = f"Сектор SHORT — подтверждает (+10)"
        elif sector_trend == 'LONG' and last_trend == -1:
            sector_mod = -10
            factors['sector'] = f"Сектор LONG, но акция SHORT — противоречие (-10)"
        elif sector_trend == 'SHORT' and last_trend == 1:
            sector_mod = -10
            factors['sector'] = f"Сектор SHORT, но акция LONG — противоречие (-10)"
        else:
            factors['sector'] = f"Сектор {sector_trend} — без влияния"
    else:
        factors['sector'] = "Сектор: нет данных"
    
    # vs Сектор (опережение/отставание)
    strength_mod = 0
    if relative_strength > 1.02:
        strength_mod = +5
        factors['strength'] = f"🟢 Опережает сектор — +5"
    elif relative_strength < 0.98:
        strength_mod = -5
        factors['strength'] = f"🔴 Отстаёт от сектора — -5"
    else:
        factors['strength'] = "⚪ Нейтрально к сектору"
    
    score += sector_mod + strength_mod
    
    # === TRIN (Индекс Армса) — модификатор ===
    trin_mod = 0
    if trin_value is not None:
        if trin_value > 1.5:
            trin_mod = -10
            factors['trin'] = f"TRIN={trin_value:.1f} (экстр. перепроданность) — штраф -10"
        elif trin_value > 1.2:
            trin_mod = -5
            factors['trin'] = f"TRIN={trin_value:.1f} (медвежий) — штраф -5"
        elif trin_value < 0.5:
            trin_mod = -10
            factors['trin'] = f"TRIN={trin_value:.1f} (экстр. перекупленность) — штраф -10"
        elif trin_value < 0.8:
            trin_mod = -5
            factors['trin'] = f"TRIN={trin_value:.1f} (перекупленность) — штраф -5"
        else:
            trin_mod = 0
            factors['trin'] = f"TRIN={trin_value:.1f} — норма"
    else:
        factors['trin'] = "TRIN: нет данных"
    
    score += trin_mod
    score = max(0, min(100, score))
    
    # Цвет и бар + уровень
    if score >= 95:
        level_emoji = "🔥"; level_text = "Идеальный"; score_bar = "██████████"
    elif score >= 80:
        level_emoji = "✅"; level_text = "Сильный"; score_bar = "██████████"
    elif score >= 60:
        level_emoji = "👀"; level_text = "Умеренный"
        bar_len = int(score / 10); score_bar = "█" * bar_len + "░" * (10 - bar_len)
    elif score >= 40:
        level_emoji = "⏳"; level_text = "Слабый"
        bar_len = int(score / 10); score_bar = "█" * bar_len + "░" * (10 - bar_len)
    else:
        level_emoji = "❌"; level_text = "Не входить"
        bar_len = max(1, int(score / 10)); score_bar = "█" * bar_len + "░" * (10 - bar_len)
    
    score_color = "🟢" if score >= 80 else "🟡" if score >= 60 else "🔴"
    score_text = f"{level_emoji} {score_color} [{score_bar}] {score}/100"
    
    return {
        'ticker': ticker,
        'close': round(last_close, 2),
        'supertrend': st_signal,
        'regime': regime_full,
        'atr': atr_text,
        'hi2': hi2_text,
        'score': score_text,
        'factors': factors,
    }
