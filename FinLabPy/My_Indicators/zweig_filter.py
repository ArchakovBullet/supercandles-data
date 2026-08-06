"""
Zweig Master Filter — объединённый сигнал для принятия решений.
Объединяет: Режим рынка + TRIN + Сессию + RVI.
Возвращает: ✅ РАЗРЕШЕНО / ⛔ ЗАПРЕЩЕНО
"""

def get_zweig_signal(market_regime, trin_value, session_status, garch_vol):
    """
    Главный фильтр Цвейга.
    
    Параметры:
    - market_regime: из get_market_regime()
    - trin_value: значение TRIN
    - session_status: из get_session_status()
    - garch_vol: средняя волатильность RVI
    
    Возвращает:
    - signal: APPROVED / BLOCKED / CAUTION
    - emoji: 🟢 / 🔴 / 🟡
    - reasons: список причин
    """
    reasons = []
    blocks = []
    warnings = []
    
    # === 1. КРИЗИС — полная блокировка ===
    if market_regime and market_regime['regime'] == 'CRISIS':
        blocks.append(f"🌪️ Режим CRISIS (RVI={garch_vol:.1f}%) — вход запрещён")
        return {
            'signal': 'BLOCKED',
            'emoji': '🔴',
            'label': '⛔ ТОРГОВЛЯ ЗАПРЕЩЕНА',
            'blocks': blocks,
            'warnings': warnings,
            'reasons': blocks + warnings,
        }
    
    # === 2. Рынок закрыт — блокировка ===
    if session_status and session_status['status'] == 'CLOSED':
        blocks.append("🔴 Рынок закрыт — вход невозможен")
        return {
            'signal': 'BLOCKED',
            'emoji': '🔴',
            'label': '⛔ РЫНОК ЗАКРЫТ',
            'blocks': blocks,
            'warnings': warnings,
            'reasons': blocks + warnings,
        }
    
    # === 3. TRIN экстремальный — блокировка ===
    if trin_value is not None:
        if trin_value > 1.5:
            warnings.append(f"🔴 TRIN={trin_value:.1f} — экстремальная перепроданность. Осторожно.")
        elif trin_value < 0.5:
            warnings.append(f"🔴 TRIN={trin_value:.1f} — экстремальная перекупленность. Осторожно.")
        elif trin_value > 1.2:
            warnings.append(f"🟠 TRIN={trin_value:.1f} — медвежий. Давление продавцов.")
        elif trin_value < 0.8:
            warnings.append(f"🟢 TRIN={trin_value:.1f} — бычий. Покупатели контролируют.")
    
    # === 4. Низкая ликвидность — предупреждение ===
    if session_status and session_status['liquidity'] < 0.5:
        warnings.append(f"🟡 Ликвидность {session_status['liquidity']:.0%} — сигналы могут быть шумовыми")
    
    # === 5. Высокий RVI — предупреждение ===
    if garch_vol and garch_vol > 25:
        warnings.append(f"🟡 RVI={garch_vol:.1f}% — высокая волатильность")
    
    # === ИТОГ ===
    if warnings:
        return {
            'signal': 'CAUTION',
            'emoji': '🟡',
            'label': '⚠️ ТОРГОВЛЯ С ОСТОРОЖНОСТЬЮ',
            'blocks': blocks,
            'warnings': warnings,
            'reasons': blocks + warnings,
        }
    
    # === ВСЁ ЧИСТО ===
    if market_regime:
        reasons.append(f"🚀 Режим {market_regime['regime']} — можно торговать")
    else:
        reasons.append("🚀 Режим: нет данных")
    reasons.append(f"📊 TRIN={trin_value:.1f} — норма" if trin_value else "📊 TRIN: нет данных")
    reasons.append(f"📈 RVI={garch_vol:.1f}% — норма" if garch_vol else "📈 RVI: нет данных")
    
    return {
        'signal': 'APPROVED',
        'emoji': '🟢',
        'label': '✅ ТОРГОВЛЯ РАЗРЕШЕНА',
        'blocks': blocks,
        'warnings': warnings,
        'reasons': reasons,
    }
