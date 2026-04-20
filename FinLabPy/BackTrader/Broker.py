import logging
from backtrader import BrokerBase

from FinLabPy.BackTrader import Store


class Broker(BrokerBase):
    params = ()

    def __init__(self, **kwargs):
        super(Broker, self).__init__()
        self.store: Store = kwargs.get('store', None)
        self.broker = self.store.broker  # Брокер из хранилища
        
        # Исправленная строка - проверяем тип broker
        if hasattr(self.broker, 'code'):
            broker_code = self.broker.code
        else:
            broker_code = str(self.broker)
            
        self.logger = logging.getLogger(f'BTBroker.{broker_code}')
        
        # Остальные атрибуты
        if hasattr(self.broker, 'get_cash'):
            self.startingcash = self.cash = self.broker.get_cash()
        else:
            self.startingcash = self.cash = 1000000.0
            
        self.commission = 0.0005
        
    def getcash(self):
        if hasattr(self.broker, 'get_cash'):
            self.cash = self.broker.get_cash()
        return self.cash
    
    def getvalue(self):
        if hasattr(self.broker, 'get_value'):
            return self.broker.get_value()
        return self.cash
    
    def buy(self, owner, data, size, price=None, plimit=None, exectype=None, valid=None, tradeid=0, **kwargs):
        self.logger.info(f'BUY: {data._dataname} {size} @ {price}')
        return None
    
    def sell(self, owner, data, size, price=None, plimit=None, exectype=None, valid=None, tradeid=0, **kwargs):
        self.logger.info(f'SELL: {data._dataname} {size} @ {price}')
        return None
