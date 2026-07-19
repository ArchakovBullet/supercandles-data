"""
Объединённый вердикт — единое решение на основе всех сигналов.
Иерархия:
  FutOI (40%) — главный фильтр
  TradeStats (30%) — сила сигнала (шорт-скор)
  Order Flow (20%) — подтверждение (OFI + Cumulative Delta)
  Тренд (10%) — контекст рынка
"""


def get_unified_verdict(signal_type, short_score, ofi, cum_delta, trend_is_up, trend_is_down,
                        support, resistance, atr, close_price, hi2_value=None):
    """
    Принимает все сигналы и возвращает единое решение с уровнями входа/выхода.
    
    Returns:
        decision: LONG / SHORT / WAIT
        long_score: 0-100
        short_score: 0-100
        confidence: низкая / средняя / высокая
        reason: текстовое пояснение
        entry_price: рекомендуемая цена входа
        stop_loss: стоп-лосс
        target: цель
        potential_pct: потенциал в %
    """
    
    # === 1. FutOI — главный фильтр (40%) ===
    futoi_score = 0
    futoi_direction = None
    
    if signal_type in ("LONG", "WAIT_FOR_RETRACEMENT"):
        futoi_score = 40
        futoi_direction = "LONG"
    elif signal_type in ("SHORT", "WAIT_FOR_BOUNCE"):
        futoi_score = -40
        futoi_direction = "SHORT"
    else:
        futoi_score = 0
        futoi_direction = "NEUTRAL"
    
    # BLOCKED — ослабленный сигнал
    if "BLOCKED" in signal_type:
        futoi_score = futoi_score * 0.5
    
    # === 2. TradeStats / шорт-скор (30%) ===
    trade_score = 0
    if short_score is not None:
        # short_score 0-100 -> чем выше, тем сильнее шорт-сигнал
        # Для лонга используем обратный скор (100 - short_score)
        trade_score = (short_score - 50) / 50 * 30  # диапазон -30 до +30
    
    # === 3. Order Flow (20%) ===
    ofi_score = 0
    if ofi is not None:
        ofi_val = ofi.get('ofi', 0)
        # OFI от -1 до +1 -> масштабируем до ±20
        ofi_score = ofi_val * 20
        
        # Дивергенция снижает вес
        if ofi.get('divergence'):
            ofi_score = ofi_score * 0.3  # ослабляем при дивергенции
    
    # Cumulative Delta
    delta_score = 0
    if cum_delta is not None:
        cd = cum_delta
        # Тренд дельты: растёт = +5, падает = -5
        if cd.get('delta_trend') == 'растёт':
            delta_score = 5
        elif cd.get('delta_trend') == 'падает':
            delta_score = -5
        
        # Дивергенция
        if cd.get('divergence'):
            delta_score = delta_score * 0.3
    
    ofi_total = ofi_score + delta_score  # суммируем OFI + CumDelta
    
    # === 4. Тренд (10%) ===
    trend_score = 0
    if trend_is_up:
        trend_score = 10
    elif trend_is_down:
        trend_score = -10
    
    # === 5. HI2 — штраф за концентрацию (до -15) ===
    hi2_penalty = 0
    if hi2_value is not None and hi2_value > 0:
        if hi2_value > 500:
            hi2_penalty = -15
        elif hi2_value > 150:
            hi2_penalty = -10
        elif hi2_value > 70:
            hi2_penalty = -5

    # === ИТОГОВЫЙ СКОР ===
    total_score = futoi_score + trade_score + ofi_total + trend_score + hi2_penalty
    
    # Определяем решение
    # Если сигнал заблокирован — не входим
    if "BLOCKED" in signal_type:
        decision = "WAIT"
        confidence = "низкая"
        reason = f"Сигнал {signal_type} — вход заблокирован. Ждать улучшения условий."
    elif futoi_direction == "NEUTRAL" and abs(total_score) < 30:
        decision = "WAIT"
        confidence = "низкая"
        reason = "Вердикт NEUTRAL, сигналы не набрали порог"
    elif total_score >= 30:
        decision = "LONG"
        if total_score >= 60:
            confidence = "высокая"
        elif total_score >= 45:
            confidence = "средняя"
        else:
            confidence = "низкая"
        reason = f"Суммарный скор {total_score:.0f}/100 — сигнал LONG"
    elif total_score <= -30:
        decision = "SHORT"
        if total_score <= -60:
            confidence = "высокая"
        elif total_score <= -45:
            confidence = "средняя"
        else:
            confidence = "низкая"
        reason = f"Суммарный скор {abs(total_score):.0f}/100 — сигнал SHORT"
    else:
        decision = "WAIT"
        confidence = "низкая"
        reason = f"Суммарный скор {total_score:.0f}/100 — недостаточно для входа"
    
    # === УРОВНИ ВХОДА/ВЫХОДА ===
    entry_price = None
    stop_loss = None
    target = None
    potential_pct = None
    
    if atr is None:
        atr = (close_price or 0) * 0.01  # 1% по умолчанию
    
    if decision == "LONG":
        entry_price = support if support else close_price
        stop_loss = entry_price - atr * 1.5 if entry_price else None
        target = resistance if resistance else (close_price + atr * 3 if close_price else None)
    elif decision == "SHORT":
        entry_price = resistance if resistance else close_price
        stop_loss = entry_price + atr * 1.5 if entry_price else None
        target = support if support else (close_price - atr * 3 if close_price else None)
    elif decision == "WAIT" and futoi_direction == "NEUTRAL":
        # Показываем оба уровня для информации
        entry_price = None
        stop_loss = None
        target = None
    
    if entry_price and target and entry_price != 0:
        potential_pct = abs(target - entry_price) / entry_price * 100
    
    # Скоры для отображения
    long_display = max(0, min(100, total_score + 50))
    short_display = max(0, min(100, 50 - total_score))
    
    return {
        'decision': decision,
        'long_score': round(long_display),
        'short_score': round(short_display),
        'confidence': confidence,
        'reason': reason,
        'total_score': round(total_score, 1),
        'futoi_contribution': round(futoi_score, 1),
        'trade_contribution': round(trade_score, 1),
        'ofi_contribution': round(ofi_total, 1),
        'trend_contribution': round(trend_score, 1),
        'hi2_penalty': round(hi2_penalty, 1),
        'entry_price': round(entry_price, 2) if entry_price else None,
        'stop_loss': round(stop_loss, 2) if stop_loss else None,
        'target': round(target, 2) if target else None,
        'potential_pct': round(potential_pct, 1) if potential_pct else None,
    }
