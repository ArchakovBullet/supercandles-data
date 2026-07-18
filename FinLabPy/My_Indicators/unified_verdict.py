"""
Объединённый вердикт — единое решение на основе всех сигналов.
Иерархия:
FutOI (40%) — главный фильтр
TradeStats (30%) — сила сигнала (шорт-скор)
Order Flow (20%) — подтверждение (OFI + Cumulative Delta)
Тренд (10%) — контекст рынка
"""

# Константы весов и порогов
FUTOI_WEIGHT = 40
TRADE_WEIGHT = 30
OFI_WEIGHT = 20
TREND_WEIGHT = 10

# Пороги для принятия решений
ENTRY_THRESHOLD = 30
HIGH_CONFIDENCE_THRESHOLD = 60
MEDIUM_CONFIDENCE_THRESHOLD = 45

# HI2 штрафы
HI2_PENALTY_500 = -15
HI2_PENALTY_150 = -10
HI2_PENALTY_70 = -5

# Риск-менеджмент
STOP_LOSS_ATR_MULTIPLIER = 1.5
TAKE_PROFIT_ATR_MULTIPLIER = 3
DEFAULT_ATR_PCT = 0.01

# Минимальная цена для расчетов (избегаем деления на ноль)
MIN_PRICE_THRESHOLD = 0.0001


def is_valid_price(price):
    """Проверяет, что цена корректна для расчетов"""
    return price is not None and isinstance(price, (int, float)) and price > MIN_PRICE_THRESHOLD


def get_numeric_value(value, default=0):
    """Безопасно извлекает числовое значение из различных типов"""
    if value is None:
        return default
    
    if isinstance(value, (int, float)):
        return float(value)
    
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def get_unified_verdict(signal_type, short_score, ofi, cum_delta, trend_is_up, trend_is_down,
                       support, resistance, atr, close_price, hi2_value=None):
    
    if not isinstance(signal_type, str):
        signal_type = str(signal_type)
    
    if "BLOCKED" in str(signal_type).upper():
        return {
            'decision': "WAIT",
            'long_score': 0,
            'short_score': 0,
            'confidence': "низкая",
            'reason': f"Сигнал {signal_type} — вход заблокирован. Ждать улучшения условий.",
            'total_score': 0,
            'futoi_contribution': 0,
            'trade_contribution': 0,
            'ofi_contribution': 0,
            'trend_contribution': 0,
            'hi2_penalty': 0,
            'entry_price': None,
            'stop_loss': None,
            'target': None,
            'potential_pct': None,
        }
    
    futoi_score = 0
    futoi_direction = None
    signal_type_str = str(signal_type).upper()
    
    if signal_type_str in ("LONG", "WAIT_FOR_RETRACEMENT"):
        futoi_score = FUTOI_WEIGHT
        futoi_direction = "LONG"
    elif signal_type_str in ("SHORT", "WAIT_FOR_BOUNCE"):
        futoi_score = -FUTOI_WEIGHT
        futoi_direction = "SHORT"
    else:
        futoi_score = 0
        futoi_direction = "NEUTRAL"
    
    trade_score = 0
    short_score_val = get_numeric_value(short_score, 50)
    
    if 0 <= short_score_val <= 100:
        trade_score = (short_score_val - 50) / 50 * TRADE_WEIGHT
    else:
        trade_score = 0
    
    ofi_score = 0
    delta_score = 0
    
    if ofi and isinstance(ofi, dict):
        ofi_val = get_numeric_value(ofi.get('ofi'), 0)
        ofi_val = max(-1.0, min(1.0, ofi_val))
        ofi_score = ofi_val * OFI_WEIGHT
        if ofi.get('divergence'):
            ofi_score = ofi_score * 0.3
    
    if cum_delta and isinstance(cum_delta, dict):
        cd = cum_delta
        delta_trend = cd.get('delta_trend')
        if delta_trend == 'растёт':
            delta_score = 5
        elif delta_trend == 'падает':
            delta_score = -5
        if cd.get('divergence'):
            delta_score = delta_score * 0.3
    
    ofi_total = ofi_score + delta_score
    
    trend_score = 0
    if trend_is_up:
        trend_score = TREND_WEIGHT
    elif trend_is_down:
        trend_score = -TREND_WEIGHT
    
    hi2_penalty = 0
    hi2_val = get_numeric_value(hi2_value, 0)
    if hi2_val > 500:
        hi2_penalty = HI2_PENALTY_500
    elif hi2_val > 150:
        hi2_penalty = HI2_PENALTY_150
    elif hi2_val > 70:
        hi2_penalty = HI2_PENALTY_70
    
    total_score = futoi_score + trade_score + ofi_total + trend_score + hi2_penalty
    
    decision = "WAIT"
    confidence = "низкая"
    reason = ""
    
    if futoi_direction == "NEUTRAL" and abs(total_score) < ENTRY_THRESHOLD:
        decision = "WAIT"
        reason = "Вердикт NEUTRAL, сигналы не набрали порог"
    elif total_score >= ENTRY_THRESHOLD:
        decision = "LONG"
        if total_score >= HIGH_CONFIDENCE_THRESHOLD:
            confidence = "высокая"
        elif total_score >= MEDIUM_CONFIDENCE_THRESHOLD:
            confidence = "средняя"
        reason = f"Суммарный скор {total_score:.0f}/100 — сигнал LONG"
    elif total_score <= -ENTRY_THRESHOLD:
        decision = "SHORT"
        if total_score <= -HIGH_CONFIDENCE_THRESHOLD:
            confidence = "высокая"
        elif total_score <= -MEDIUM_CONFIDENCE_THRESHOLD:
            confidence = "средняя"
        reason = f"Суммарный скор {abs(total_score):.0f}/100 — сигнал SHORT"
    else:
        reason = f"Суммарный скор {total_score:.0f}/100 — недостаточно для входа"
    
    entry_price = None
    stop_loss = None
    target = None
    potential_pct = None
    
    safe_atr = get_numeric_value(atr)
    if safe_atr is None or safe_atr <= 0:
        safe_close = get_numeric_value(close_price, 100)
        safe_atr = safe_close * DEFAULT_ATR_PCT
    
    safe_close_price = get_numeric_value(close_price)
    safe_support = get_numeric_value(support)
    safe_resistance = get_numeric_value(resistance)
    
    if decision == "LONG":
        if is_valid_price(safe_support) and safe_support < (safe_close_price or float('inf')):
            entry_price = safe_support
        elif is_valid_price(safe_close_price):
            entry_price = safe_close_price
        if entry_price and safe_atr > 0:
            stop_loss = entry_price - safe_atr * STOP_LOSS_ATR_MULTIPLIER
            if is_valid_price(safe_resistance) and safe_resistance > entry_price:
                target = safe_resistance
            else:
                target = entry_price + safe_atr * TAKE_PROFIT_ATR_MULTIPLIER
    elif decision == "SHORT":
        if is_valid_price(safe_resistance) and safe_resistance > (safe_close_price or 0):
            entry_price = safe_resistance
        elif is_valid_price(safe_close_price):
            entry_price = safe_close_price
        if entry_price and safe_atr > 0:
            stop_loss = entry_price + safe_atr * STOP_LOSS_ATR_MULTIPLIER
            if is_valid_price(safe_support) and safe_support < entry_price:
                target = safe_support
            else:
                target = entry_price - safe_atr * TAKE_PROFIT_ATR_MULTIPLIER
    
    if entry_price and target and is_valid_price(entry_price):
        if abs(entry_price) > MIN_PRICE_THRESHOLD:
            potential_pct = abs(target - entry_price) / abs(entry_price) * 100
    
    long_display = 0
    short_display = 0
    
    if decision == "LONG":
        base_score = 50
        additional = min(50, max(0, (total_score - ENTRY_THRESHOLD) / (100 - ENTRY_THRESHOLD) * 50))
        long_display = round(base_score + additional)
        short_display = max(0, 100 - long_display)
    elif decision == "SHORT":
        base_score = 50
        additional = min(50, max(0, (abs(total_score) - ENTRY_THRESHOLD) / (100 - ENTRY_THRESHOLD) * 50))
        short_display = round(base_score + additional)
        long_display = max(0, 100 - short_display)
    else:
        long_display = max(0, min(100, 50 + total_score))
        short_display = max(0, min(100, 50 - total_score))
    
    return {
        'decision': decision,
        'long_score': long_display,
        'short_score': short_display,
        'confidence': confidence,
        'reason': reason,
        'total_score': round(total_score, 1),
        'futoi_contribution': round(futoi_score, 1),
        'trade_contribution': round(trade_score, 1),
        'ofi_contribution': round(ofi_total, 1),
        'trend_contribution': round(trend_score, 1),
        'hi2_penalty': round(hi2_penalty, 1),
        'entry_price': round(entry_price, 2) if entry_price is not None else None,
        'stop_loss': round(stop_loss, 2) if stop_loss is not None else None,
        'target': round(target, 2) if target is not None else None,
        'potential_pct': round(potential_pct, 1) if potential_pct is not None else None,
    }
