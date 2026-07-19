"""
Объединённый сканер фьючерсов — вердикт на основе 1D + 4H + 1H.
Учитывает: fiz_buy_ratio, HI2, GARCH, тренд, OFI, CumDelta, дистрибуцию/аккумуляцию.

Веса ТФ: 1D=50%, 4H=30%, 1H=20%
"""

import pandas as pd
import numpy as np


def get_tf_signal(df, tf_name):
    """Сигнал для одного таймфрейма на основе fiz_buy_ratio."""
    if df is None or len(df) < 3:
        return 'NEUTRAL', 50, {}
    
    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) >= 2 else latest
    
    fiz_buy = latest.get('fiz_buy_ratio', 50)
    fiz_delta = fiz_buy - prev.get('fiz_buy_ratio', fiz_buy)
    
    if fiz_buy > 60 and fiz_delta > 0:
        signal = 'LONG'
        score = min(85, 50 + (fiz_buy - 60) * 1.5 + fiz_delta * 10)
    elif fiz_buy < 40 and fiz_delta < 0:
        signal = 'SHORT'
        score = min(85, 50 + (40 - fiz_buy) * 1.5 + abs(fiz_delta) * 10)
    else:
        signal = 'NEUTRAL'
        score = 50 + fiz_delta * 5
    
    return signal, round(score), {
        'fiz_buy': round(fiz_buy, 1),
        'fiz_delta': round(fiz_delta, 2),
    }


def get_unified_scanner_verdict(df_d1, df_4h, df_1h, 
                                 d1_trend_up=False, d1_trend_down=False,
                                 hi2_value=None, garch_vol=0,
                                 ofi=None, cum_delta=None,
                                 is_distribution=False, is_accumulation=False, hpi_signal=None, hpi_divergence=False, zweig_signal=None):
    """
    Объединённый вердикт по трём таймфреймам + рыночные факторы.
    
    Учитываемые факторы:
    - ТФ сигналы (fiz_buy_ratio): 1D=50%, 4H=30%, 1H=20% — БАЗА (60% веса)
    - HI2 (концентрация): >300 = риск, >500 = экстремальный риск — ШТРАФ (15%)
    - GARCH (волатильность): >25% = риск, >35% = блокировка — ШТРАФ (10%)
    - Тренд D1: против сигнала = ослабление — МОДИФИКАТОР (10%)
    - Дистрибуция/Аккумуляция: дистрибуция при LONG = минус — МОДИФИКАТОР (5%)
    
    Возвращает:
    - decision, score, confidence, recommendation
    - factors: детализация вклада каждого фактора
    """
    
    # === 1. Сигналы по ТФ (БАЗА — 60%) ===
    sig_d1, score_d1, det_d1 = get_tf_signal(df_d1, '1D')
    sig_4h, score_4h, det_4h = get_tf_signal(df_4h, '4H')
    sig_1h, score_1h, det_1h = get_tf_signal(df_1h, '1H')
    
    def sig_to_val(s):
        return 1 if s == 'LONG' else (-1 if s == 'SHORT' else 0)
    
    val_d1 = sig_to_val(sig_d1)
    val_4h = sig_to_val(sig_4h)
    val_1h = sig_to_val(sig_1h)
    
    # Взвешенный ТФ-скор
    tf_weighted = val_d1 * 0.50 + val_4h * 0.30 + val_1h * 0.20
    tf_score = 50 + tf_weighted * 50  # 0-100
    
    # === 2. HI2 — штраф за концентрацию (15%) ===
    hi2_penalty = 0
    hi2_note = ""
    if hi2_value is not None:
        if hi2_value > 500:
            hi2_penalty = -15
            hi2_note = f"🔴 HI2={hi2_value:.0f} (экстремальная) — штраф {hi2_penalty}"
        elif hi2_value > 300:
            hi2_penalty = -8
            hi2_note = f"🟡 HI2={hi2_value:.0f} (очень высокая) — штраф {hi2_penalty}"
        elif hi2_value > 150:
            hi2_penalty = -3
            hi2_note = f"⚪ HI2={hi2_value:.0f} (высокая) — штраф {hi2_penalty}"
        else:
            hi2_note = f"✅ HI2={hi2_value:.0f} — норма"
    
    # === 3. GARCH — штраф за волатильность (10%) ===
    garch_penalty = 0
    garch_note = ""
    if garch_vol > 35:
        garch_penalty = -30  # Блокировка
        garch_note = f"🔴 GARCH={garch_vol:.1f}% (экстремальная) — БЛОКИРОВКА ({garch_penalty})"
    elif garch_vol > 25:
        garch_penalty = -8
        garch_note = f"🟡 GARCH={garch_vol:.1f}% (высокая) — штраф {garch_penalty}"
    elif garch_vol > 15:
        garch_penalty = -2
        garch_note = f"⚪ GARCH={garch_vol:.1f}% (повышенная) — штраф {garch_penalty}"
    else:
        garch_note = f"✅ GARCH={garch_vol:.1f}% — норма"
    
    # === 4. Тренд D1 — модификатор (10%) ===
    trend_mod = 0
    trend_note = ""
    if d1_trend_up:
        if tf_weighted > 0:
            trend_mod = +5
            trend_note = "✅ Тренд бычий — подтверждает LONG (+5)"
        elif tf_weighted < 0:
            trend_mod = -5
            trend_note = "⚠️ Тренд бычий, но сигнал SHORT — противоречие (-5)"
        else:
            trend_note = "📈 Тренд бычий, сигнал нейтральный"
    elif d1_trend_down:
        if tf_weighted < 0:
            trend_mod = +5
            trend_note = "✅ Тренд медвежий — подтверждает SHORT (+5)"
        elif tf_weighted > 0:
            trend_mod = -5
            trend_note = "⚠️ Тренд медвежий, но сигнал LONG — противоречие (-5)"
        else:
            trend_note = "📉 Тренд медвежий, сигнал нейтральный"
    else:
        trend_note = "◼ Тренд боковой — без влияния"
    
    # === 5. Дистрибуция/Аккумуляция (5%) ===
    distr_mod = 0
    distr_note = ""
    if is_distribution and tf_weighted > 0:
        distr_mod = -5
        distr_note = "⚠️ Дистрибуция при сигнале LONG — ослабление (-5)"
    elif is_accumulation and tf_weighted < 0:
        distr_mod = -5
        distr_note = "⚠️ Аккумуляция при сигнале SHORT — ослабление (-5)"
    elif is_distribution:
        distr_mod = +3
        distr_note = "✅ Дистрибуция — подтверждает SHORT (+3)"
    elif is_accumulation:
        distr_mod = +3
        distr_note = "✅ Аккумуляция — подтверждает LONG (+3)"
    else:
        distr_note = "⚪ Нет выраженной дистрибуции/аккумуляции"
    
    # === HPI (Индекс Херрика) — модификатор ===
    hpi_mod = 0
    hpi_note = ""
    if hpi_signal is not None:
        if hpi_signal == 'LONG' and tf_weighted > 0:
            hpi_mod = +5
            hpi_note = "✅ HPI LONG — подтверждает (+5)"
        elif hpi_signal == 'SHORT' and tf_weighted < 0:
            hpi_mod = +5
            hpi_note = "✅ HPI SHORT — подтверждает (+5)"
        elif hpi_signal == 'LONG' and tf_weighted < 0:
            hpi_mod = -5
            hpi_note = "⚠️ HPI LONG, но сигнал SHORT — противоречие (-5)"
        elif hpi_signal == 'SHORT' and tf_weighted > 0:
            hpi_mod = -5
            hpi_note = "⚠️ HPI SHORT, но сигнал LONG — противоречие (-5)"
        else:
            hpi_note = f"HPI {hpi_signal} — нейтрально"
        
        if hpi_divergence:
            hpi_mod -= 10
            hpi_note += " | ⚠️ Дивергенция HPI (-10)"
    else:
        hpi_note = "HPI: нет данных"
    
    # === ZWEIG FILTER — модификатор ===
    zweig_mod = 0
    zweig_note = ""
    if zweig_signal is not None:
        if zweig_signal == 'BLOCKED':
            zweig_mod = -100  # Фактически обнуляет скор
            zweig_note = "⛔ Zweig: ТОРГОВЛЯ ЗАПРЕЩЕНА — скор обнулён"
        elif zweig_signal == 'CAUTION':
            zweig_mod = -5
            zweig_note = "⚠️ Zweig: ОСТОРОЖНО — штраф -5"
        else:
            zweig_note = "✅ Zweig: РАЗРЕШЕНО"
    else:
        zweig_note = "Zweig: нет данных"
    
    # === ИТОГОВЫЙ СКОР ===
    total_mod = hi2_penalty + garch_penalty + trend_mod + distr_mod + hpi_mod + zweig_mod
    final_score = tf_score + total_mod
    final_score = max(0, min(100, final_score))
    
    # === РЕШЕНИЕ ===
    if garch_vol > 35:
        decision = 'WAIT'
        confidence = 'низкая'
        recommendation = f'⛔ GARCH={garch_vol:.1f}% > 35% — вход заблокирован. Ждать снижения волатильности.'
    elif tf_weighted >= 0.4 and final_score >= 60:
        decision = 'LONG'
    elif tf_weighted <= -0.4 and final_score >= 60:
        decision = 'SHORT'
    else:
        decision = 'WAIT'
    
    # Уверенность
    if final_score >= 80:
        confidence = 'высокая'
    elif final_score >= 55:
        confidence = 'средняя'
    else:
        confidence = 'низкая'
    
    # Рекомендация
    if decision == 'LONG' and confidence == 'высокая':
        recommendation = '✅ Все факторы подтверждают LONG. Можно входить.'
    elif decision == 'LONG' and confidence == 'средняя':
        recommendation = '✅ LONG, но есть ослабляющие факторы. Проверить детали.'
    elif decision == 'SHORT' and confidence == 'высокая':
        recommendation = '✅ Все факторы подтверждают SHORT. Можно входить.'
    elif decision == 'SHORT' and confidence == 'средняя':
        recommendation = '✅ SHORT, но есть ослабляющие факторы. Проверить детали.'
    elif garch_vol > 35:
        recommendation = f'⛔ GARCH={garch_vol:.1f}% > 35% — вход заблокирован.'
    else:
        recommendation = '⏳ Сигналы противоречивы. Ждать согласованности факторов.'
    
    # Тренд
    trend_text = '📈 Бычий' if d1_trend_up else ('📉 Медвежий' if d1_trend_down else '◼ Боковик')
    
    return {
        'decision': decision,
        'score': round(final_score),
        'confidence': confidence,
        'recommendation': recommendation,
        'weighted_val': round(tf_weighted, 2),
        'trend': trend_text,
        'signals': {
            '1D': {'signal': sig_d1, 'score': score_d1, 'details': det_d1},
            '4H': {'signal': sig_4h, 'score': score_4h, 'details': det_4h},
            '1H': {'signal': sig_1h, 'score': score_1h, 'details': det_1h},
        },
        'factors': {
            'tf_score': round(tf_score, 1),
            'tf_weighted': round(tf_weighted, 2),
            'hi2_penalty': hi2_penalty,
            'hi2_note': hi2_note,
            'garch_penalty': garch_penalty,
            'garch_note': garch_note,
            'trend_mod': trend_mod,
            'trend_note': trend_note,
            'distr_mod': distr_mod,
            'distr_note': distr_note,
            'hpi_mod': hpi_mod, 'hpi_note': hpi_note,
            'zweig_mod': zweig_mod, 'zweig_note': zweig_note,
            'total_mod': total_mod,
        }
    }
