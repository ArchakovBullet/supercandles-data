"""
Риск-менеджмент: расчёт ГО, размера позиции, рисков
"""

LOT_SIZES = {
    'CNYRUBF': 1000,
    'GAZPF': 10,
    'GLDRUBF': 10,
    'IMOEXF': 10,
    'SBERF': 10,
}

GO_RATE = 0.10  # 10% — консервативная ставка ГО


def calculate_risk(ticker, close_price, atr=None, deposit=100000, stop_loss_pct=None):
    """
    Рассчитывает риск-параметры для тикера.
    
    Возвращает:
    - contract_cost: стоимость контракта
    - go: гарантийное обеспечение
    - max_lots: максимальное количество лотов на депозит
    - position_cost: стоимость позиции (1 лот)
    - risk_per_lot: риск на 1 лот в рублях (при стопе = ATR)
    - leverage: плечо
    """
    lot = LOT_SIZES.get(ticker, 10)
    contract_cost = close_price * lot
    go = contract_cost * GO_RATE
    
    max_lots = int(deposit / go) if go > 0 else 0
    position_cost = go  # Затраты на 1 лот = ГО
    
    # Риск на лот при стопе = ATR (если нет явного стоп-лосса)
    if atr is None and stop_loss_pct is None:
        stop_loss_pct = 1.0  # По умолчанию 1%
    
    if stop_loss_pct:
        risk_per_lot = contract_cost * stop_loss_pct / 100
    elif atr:
        risk_per_lot = atr * lot
    else:
        risk_per_lot = contract_cost * 0.01
    
    # Плечо
    leverage = contract_cost / go if go > 0 else 0
    
    return {
        'contract_cost': contract_cost,
        'go': go,
        'max_lots': max_lots,
        'position_cost': position_cost,
        'risk_per_lot': risk_per_lot,
        'leverage': leverage,
        'deposit': deposit,
        'lot_size': lot,
    }
