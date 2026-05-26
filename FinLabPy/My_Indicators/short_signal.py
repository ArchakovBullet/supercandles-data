"""
Модуль шорт-сигнала для FutOI стратегий.
Зеркальная логика long-сигнала: ищет оптимальные условия для входа в шорт.
"""

from typing import Tuple


class ShortSignalAnalyzer:
    """Анализатор шорт-сигналов на основе позиций физиков и юриков."""
    
    def __init__(self, ticker: str):
        self.ticker = ticker
        
    def get_short_score(self,
                        jur_pct_sell: float,
                        phys_pct_buy: float,
                        price_vs_poc: float,
                        volatility_percent: float,
                        trend: str) -> Tuple[float, str, list]:
        """Рассчитывает score для шорта (0-100)."""
        reasons = []
        score = 0
        max_score = 0
        
        if jur_pct_sell > 55:
            score += 35
            reasons.append(f"Юрики активно продают ({jur_pct_sell:.0f}%)")
        elif jur_pct_sell > 50:
            score += 20
            reasons.append(f"Юрики продают ({jur_pct_sell:.0f}%)")
        else:
            reasons.append(f"Юрики недостаточно продают ({jur_pct_sell:.0f}%)")
        max_score += 35
        
        if phys_pct_buy > 70:
            score += 25
            reasons.append(f"Физики перекуплены ({phys_pct_buy:.0f}%)")
        elif phys_pct_buy > 60:
            score += 15
            reasons.append(f"Физики покупают ({phys_pct_buy:.0f}%)")
        max_score += 25
        
        if price_vs_poc < 0:
            score += 20
            reasons.append("Цена ниже POC")
        else:
            reasons.append("Цена выше POC — риск отскока")
        max_score += 20
        
        if trend == 'нисходящий':
            score += 15
            reasons.append("Нисходящий тренд")
        elif trend == 'боковик':
            score += 5
            reasons.append("Боковик — шорт от сопротивления")
        max_score += 15
        
        if 1 < volatility_percent < 3:
            score += 5
            reasons.append("Волатильность умеренная")
        elif volatility_percent >= 3:
            reasons.append(f"Высокая волатильность ({volatility_percent:.1f}%)")
        max_score += 5
        
        score_pct = (score / max_score * 100) if max_score > 0 else 0
        
        if score_pct >= 70:
            verdict = "ВХОД В ШОРТ"
        elif score_pct >= 55:
            verdict = "ШОРТ ВОЗМОЖЕН"
        elif score_pct >= 40:
            verdict = "ЖДАТЬ"
        else:
            verdict = "ШОРТ НЕ РЕКОМЕНДОВАН"
        
        return score_pct, verdict, reasons
    
    def calculate_net_positions(self, phys_buy_pct: float, jur_sell_pct: float) -> dict:
        """Расчёт чистых позиций."""
        phys_net = phys_buy_pct - (100 - phys_buy_pct)
        jur_net = jur_sell_pct - (100 - jur_sell_pct)
        
        if phys_net > 50:
            phys_verdict = "Экстремально перекуплены"
        elif phys_net > 30:
            phys_verdict = "Перекуплены"
        elif phys_net < -30:
            phys_verdict = "Перепроданы"
        else:
            phys_verdict = "Нейтрально"
            
        if jur_net > 40:
            jur_verdict = "Агрессивный шорт юриков"
        elif jur_net > 20:
            jur_verdict = "Юрики в шорте"
        elif jur_net < -20:
            jur_verdict = "Юрики в лонге"
        else:
            jur_verdict = "Нейтрально"
        
        return {'phys_net': phys_net, 'jur_net': jur_net,
                'phys_verdict': phys_verdict, 'jur_verdict': jur_verdict}
    
    def calculate_risk(self, entry_price: float, atr: float, capital: float,
                       risk_percent: float = 2.0) -> dict:
        """Расчёт рисков для шорт-позиции."""
        risk_amount = capital * risk_percent / 100
        stop_loss = entry_price + atr * 1.5
        take_profit = entry_price - atr * 3.0
        risk_per_unit = stop_loss - entry_price
        position_size = risk_amount / risk_per_unit if risk_per_unit > 0 else 0
        
        return {
            'entry': entry_price, 'stop_loss': stop_loss, 'take_profit': take_profit,
            'risk_per_unit': risk_per_unit, 'max_risk_rub': risk_amount,
            'max_risk_pct': risk_percent, 'position_size': int(position_size),
            'risk_reward_ratio': round((entry_price - take_profit) / (stop_loss - entry_price), 1)
        }
