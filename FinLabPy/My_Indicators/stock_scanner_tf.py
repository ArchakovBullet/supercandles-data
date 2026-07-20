"""
Трёхтаймфреймовый скринер акций: 1D + 4H + 1H.
Учитывает: SuperTrend, ADX, Choppiness, HI2, GARCH, тренд SMA20.
Веса ТФ: 1D=50%, 4H=30%, 1H=20%
"""

import pandas as pd
import numpy as np
from My_Indicators.stock_screener import calculate_supertrend, calculate_adx, calculate_choppiness


def get_stock_tf_signal(df, tf_name):
    """Сигнал для одного ТФ акции на основе SuperTrend + ADX."""
    if df is None or len(df) < 30:
        return 'NEUTRAL', 50, {}
    
    trend, st_line = calculate_supertrend(df)
    adx = calculate_adx(df)
    chop = calculate_choppiness(df)
    
    last_trend = trend.iloc[-1] if len(trend) > 0 else 0
    last_adx = adx.iloc[-1] if len(adx) > 0 else 0
    last_chop = chop.iloc[-1] if len(chop) > 0 else 50
    
    # Сигнал
    if last_trend == 1 and last_adx > 20 and last_chop < 62:
        signal = 'LONG'
        score = min(85, 50 + last_adx * 0.5 + (50 - last_chop) * 0.3)
    elif last_trend == -1 and last_adx > 20 and last_chop < 62:
        signal = 'SHORT'
        score = min(85, 50 + last_adx * 0.5 + (50 - last_chop) * 0.3)
    else:
        signal = 'NEUTRAL'
        score = 50 + last_adx * 0.1
    
    return signal, round(score), {
        'adx': round(last_adx, 1),
        'chop': round(last_chop, 1),
        'trend': 'LONG' if last_trend == 1 else 'SHORT' if last_trend == -1 else '—',
    }


def get_stock_scanner_verdict(df_d1, df_4h, df_1h, hi2_value=None, garch_vol=0, sector_trend=None, chop_val=None, adx_val=None, atr_pct=1.0, relative_strength=1.0, volume_spike=False):
    """
    Объединённый вердикт для акций по трём ТФ.
    """
    sig_d1, score_d1, det_d1 = get_stock_tf_signal(df_d1, '1D')
    sig_4h, score_4h, det_4h = get_stock_tf_signal(df_4h, '4H')
    sig_1h, score_1h, det_1h = get_stock_tf_signal(df_1h, '1H')
    
    def sig_to_val(s):
        return 1 if s == 'LONG' else (-1 if s == 'SHORT' else 0)
    
    val_d1 = sig_to_val(sig_d1)
    val_4h = sig_to_val(sig_4h)
    val_1h = sig_to_val(sig_1h)
    
    tf_weighted = val_d1 * 0.50 + val_4h * 0.30 + val_1h * 0.20
    tf_score = 50 + abs(tf_weighted) * 50  # 0 для NEUTRAL, 100 для LONG/SHORT
    
    # HI2
    hi2_penalty = 0
    hi2_note = ""
    if hi2_value is not None:
        if hi2_value > 500:
            hi2_penalty = -15
            hi2_note = f"HI2={hi2_value:.0f} (>500) — штраф -15"
        elif hi2_value > 300:
            hi2_penalty = -8
            hi2_note = f"HI2={hi2_value:.0f} (>300) — штраф -8"
        elif hi2_value > 150:
            hi2_penalty = -3
            hi2_note = f"HI2={hi2_value:.0f} (>150) — штраф -3"
        else:
            hi2_note = f"HI2={hi2_value:.0f} — норма"
    
    # GARCH
    garch_penalty = 0
    garch_note = ""
    if garch_vol > 35:
        garch_penalty = -30
        garch_note = f"GARCH={garch_vol:.1f}% (>35%) — БЛОКИРОВКА"
    elif garch_vol > 25:
        garch_penalty = -8
        garch_note = f"GARCH={garch_vol:.1f}% (>25%) — штраф -8"
    elif garch_vol > 15:
        garch_penalty = -2
        garch_note = f"GARCH={garch_vol:.1f}% (>15%) — штраф -2"
    else:
        garch_note = f"GARCH={garch_vol:.1f}% — норма"
    
    # Предварительное решение (для сектора)
    if tf_weighted >= 0.2:
        tf_decision = 'LONG'
    elif tf_weighted <= -0.2:
        tf_decision = 'SHORT'
    else:
        tf_decision = 'NEUTRAL'
    
    # Сектор (модификатор ±10)
    sector_mod = 0
    sector_note = ""
    if sector_trend is not None:
        if sector_trend == tf_decision and tf_decision in ('LONG', 'SHORT'):
            sector_mod = +10
            sector_note = f"Сектор {sector_trend} — подтверждает (+10)"
        elif sector_trend != 'NEUTRAL' and tf_decision in ('LONG', 'SHORT') and sector_trend != tf_decision:
            sector_mod = -10
            sector_note = f"Сектор {sector_trend} — противоречит (-10)"
        else:
            sector_note = f"Сектор {sector_trend} — без влияния"
    else:
        sector_note = "Сектор: нет данных"
    
    # === РЕЖИМ (Choppiness + ADX) — модификатор ===
    if chop_val is not None and adx_val is not None:
        if chop_val < 38 and adx_val > 25:
            regime_mod = +10
            regime_note = f"🚀 Тренд (Chop={chop_val:.0f}, ADX={adx_val:.0f}) — +10"
        elif chop_val > 62 and adx_val < 20:
            regime_mod = -20
            regime_note = f"🔄 Флэт (Chop={chop_val:.0f}, ADX={adx_val:.0f}) — -20"
        else:
            regime_mod = -10
            regime_note = f"⚠️ Переходный (Chop={chop_val:.0f}, ADX={adx_val:.0f}) — -10"
    else:
        regime_mod = 0
        regime_note = "Режим: нет данных"
    
    # === ATR — модификатор ===
    if atr_pct > 2.5:
        atr_mod = -5
        atr_note = f"ATR={atr_pct:.1f}% (высокая) — риск -5"
    elif atr_pct < 1.0:
        atr_mod = +5
        atr_note = f"ATR={atr_pct:.1f}% (низкая) — стабильность +5"
    else:
        atr_mod = 0
        atr_note = f"ATR={atr_pct:.1f}% — норма"
    
    # === vs Сектор (опережение/отставание) — модификатор ===
    if relative_strength > 1.02:
        strength_mod = +5
        strength_note = f"🟢 Опережает сектор (RS={relative_strength:.3f}) — +5"
    elif relative_strength < 0.98:
        strength_mod = -5
        strength_note = f"🔴 Отстаёт от сектора (RS={relative_strength:.3f}) — -5"
    else:
        strength_mod = 0
        strength_note = f"⚪ Нейтрально к сектору (RS={relative_strength:.3f})"
    
    # Volume Spike модификатор
    volume_mod = 0
    volume_note = ""
    if volume_spike:
        if tf_weighted > 0:
            volume_mod = +5
            volume_note = "📊 Volume Spike! Аномальный объём подтверждает LONG (+5)"
        elif tf_weighted < 0:
            volume_mod = +5
            volume_note = "📊 Volume Spike! Аномальный объём подтверждает SHORT (+5)"
        else:
            volume_mod = +3
            volume_note = "📊 Volume Spike! Аномальный объём — возможно движение (+3)"

    # === КОМБИНИРОВАННЫЙ СИГНАЛ (HI2 + ADX + тренд) ===
    combo_signal = "⚪ —"
    try:
        _combo_score = 0
        if hi2_value and hi2_value > 500: _combo_score -= 1
        if adx_val and adx_val > 25: _combo_score += 1
        if tf_weighted > 0: _combo_score += 1
        if tf_weighted < 0: _combo_score -= 1
        if _combo_score >= 2:
            combo_signal = "🟢 LONG"
        elif _combo_score <= -1:
            combo_signal = "🔴 SHORT"
    except:
        pass

    final_score = tf_score + hi2_penalty + garch_penalty + sector_mod + regime_mod + atr_mod + strength_mod + volume_mod
    final_score = max(0, min(100, final_score))
    
    if garch_vol > 35:
        decision = 'WAIT'
        confidence = 'низкая'
    elif tf_weighted >= 0.4 and final_score >= 60:
        decision = 'LONG'
    elif tf_weighted <= -0.4 and final_score >= 60:
        decision = 'SHORT'
    else:
        decision = 'WAIT'
    
    if final_score >= 80:
        confidence = 'высокая'
    elif final_score >= 55:
        confidence = 'средняя'
    else:
        confidence = 'низкая'
    
    return {
        'decision': decision,
        'combo_signal': combo_signal,
        'score': round(final_score),
        'confidence': confidence,
        'signals': {
            '1D': {'signal': sig_d1, 'score': score_d1},
            '4H': {'signal': sig_4h, 'score': score_4h},
            '1H': {'signal': sig_1h, 'score': score_1h},
        },
        'factors': {
            'tf_score': round(tf_score, 1),
            'hi2_note': hi2_note,
            'garch_note': garch_note,
                        'sector_mod': sector_mod, 'sector_note': sector_note,
            'regime_mod': regime_mod, 'regime_note': regime_note,
            'atr_mod': atr_mod, 'atr_note': atr_note,
            'strength_mod': strength_mod, 'strength_note': strength_note,
        'volume_mod': volume_mod, 'volume_note': volume_note,
            'hi2_penalty': hi2_penalty,
            'garch_penalty': garch_penalty,
        }
    }
