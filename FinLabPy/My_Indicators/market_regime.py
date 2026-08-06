"""
Температура рынка — определение текущей фазы.
Тренд / Флэт / Кризис
"""

import pandas as pd
import numpy as np


def get_market_regime(df_indices=None, garch_vol=None, rvi_val=None, imoex_trend=None, rgbi_change=0, avg_sector_change=0):
    """
    Определяет режим рынка на основе индикаторов.
    
    Параметры:
    - df_indices: DataFrame с колонками ADX, Choppiness (опционально)
    - garch_vol: текущая волатильность RVI
    - rvi_val: значение RVI (индекс волатильности)
    - imoex_trend: тренд IMOEX ('UP'/'DOWN'/'FLAT')
    - rgbi_change: изменение RGBI за 5 дней (%)
    - avg_sector_change: среднее изменение секторов за 5 дней (%)
    
    Возвращает:
    - regime: 'TREND' / 'FLAT' / 'CRISIS' / 'NEUTRAL'
    - score: 0-100 (0 = кризис, 100 = сильный тренд)
    - recommendation: текстовая рекомендация
    - risk_level: 0-100 (0 = без риска, 100 = максимальный риск)
    """
    
    regime = 'NEUTRAL'
    score = 50
    risk_level = 50
    reasons = []
    recommendation = "⚠️ Недостаточно данных для определения режима"
    
    # === 1. Объективные индексы (всегда показываем) ===
    if imoex_trend:
        if imoex_trend == 'UP':
            reasons.append(f"IMOEX растёт — рынок бычий")
        elif imoex_trend == 'DOWN':
            reasons.append(f"IMOEX падает — рынок медвежий")
        else:
            reasons.append(f"IMOEX в боковике")
    
    if rgbi_change < -1:
        reasons.append(f"RGBI падает ({rgbi_change:+.1f}%) — деньги уходят из облигаций")
    elif rgbi_change > 1:
        reasons.append(f"RGBI растёт ({rgbi_change:+.1f}%) — спрос на защитные активы")
    
    if avg_sector_change > 1:
        reasons.append(f"Сектора растут ({avg_sector_change:+.1f}%) — широкий рынок")
    elif avg_sector_change < -1:
        reasons.append(f"Сектора падают ({avg_sector_change:+.1f}%) — слабость рынка")

    # === 2. Проверка на КРИЗИС ===
    crisis = False
    if garch_vol is not None and garch_vol > 40:
        crisis = True
        reasons.append(f"RVI={garch_vol:.1f} п. > 30% — экстремальная волатильность")
    if rvi_val is not None and rvi_val > 40:
        crisis = True
        reasons.append(f"RVI={rvi_val:.1f} > 40 — паника на рынке")
    
    if crisis:
        regime = 'CRISIS'
        score = max(0, 50 - (garch_vol or 0) * 1.5)
        risk_level = min(100, 50 + (garch_vol or 0) * 1.5)
        recommendation = "🌪️ КРИЗИС: запрет на вход. Защитить капитал. Рассмотреть выход из позиций."
        return {
            'regime': regime,
            'score': round(score),
            'risk_level': round(risk_level),
            'recommendation': recommendation,
            'reasons': reasons,
            'imoex_trend': imoex_trend,
            'rgbi_change': round(rgbi_change, 1),
            'avg_sector_change': round(avg_sector_change, 1),
        }
    
    # === 2. Проверка на ТРЕНД / ФЛЭТ ===
    if df_indices is not None and len(df_indices) > 0:
        avg_adx = df_indices['adx'].mean() if 'adx' in df_indices.columns else 0
        avg_chop = df_indices['choppiness'].mean() if 'choppiness' in df_indices.columns else 50
        
        if avg_adx > 25 and avg_chop < 38:
            regime = 'TREND'
            score = min(100, 50 + avg_adx * 0.8 + (50 - avg_chop) * 0.5)
            risk_level = max(0, 50 - avg_adx * 0.3)
            reasons.append(f"ADX={avg_adx:.0f} (>25), Chop={avg_chop:.0f} (<38) — трендовый рынок")
            recommendation = "🚀 ТРЕНД: можно торговать по сигналам скринера. Сигналы надёжны."
        elif avg_adx < 20 and avg_chop > 62:
            regime = 'FLAT'
            score = max(0, 50 - (62 - avg_chop) * 0.5 - (20 - avg_adx) * 0.5)
            risk_level = min(100, 50 + (62 - avg_chop) * 0.5)
            reasons.append(f"ADX={avg_adx:.0f} (<20), Chop={avg_chop:.0f} (>62) — флэтовый рынок")
            recommendation = "🔄 ФЛЭТ: не входить. Ждать пробоя уровней."
        else:
            regime = 'NEUTRAL'
            score = 50
            risk_level = 50
            reasons.append(f"ADX={avg_adx:.0f}, Chop={avg_chop:.0f} — переходный рынок")
            recommendation = "⚠️ ПЕРЕХОДНЫЙ: осторожно. Сигналы могут быть ложными."
    
    return {
        'regime': regime,
        'score': round(score),
        'risk_level': round(risk_level),
        'recommendation': recommendation,
        'reasons': reasons,
    }


def get_risk_on_off(df_stocks, df_gold=None):
    """
    Определяет Risk-On / Risk-Off.
    Risk-On: акции растут, золото падает.
    Risk-Off: акции падают, золото растёт.
    """
    if df_stocks is None or len(df_stocks) < 5:
        return 'NEUTRAL', 'Недостаточно данных'
    
    stock_change = df_stocks['close'].iloc[-1] / df_stocks['close'].iloc[-5] - 1
    
    if df_gold is not None and len(df_gold) >= 5:
        gold_change = df_gold['close'].iloc[-1] / df_gold['close'].iloc[-5] - 1
        
        if stock_change > 0.02 and gold_change < 0:
            return 'RISK_ON', '📈 Risk-On: инвесторы покупают рисковые активы'
        elif stock_change < -0.02 and gold_change > 0:
            return 'RISK_OFF', '📉 Risk-Off: инвесторы уходят в защитные активы'
    
    if stock_change > 0.02:
        return 'RISK_ON', '📈 Рынок растёт'
    elif stock_change < -0.02:
        return 'RISK_OFF', '📉 Рынок падает'
    
    return 'NEUTRAL', '⚪ Боковое движение'
