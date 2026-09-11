from datetime import datetime
import backtrader as bt

class MyCSVData(bt.feeds.GenericCSVData):
    params = (
        ('dtformat', '%Y-%m-%d %H:%M:%S'),
        ('datetime', 0),
        ('open', 1),
        ('high', 2),
        ('low', 3),
        ('close', 4),
        ('volume', 5),
        ('openinterest', -1),
    )

class TestStrategy(bt.Strategy):
    def next(self):
        print(f'{self.data.datetime.date(0)} | Close: {self.data.close[0]:.2f}')

if __name__ == '__main__':
    cerebro = bt.Cerebro(stdstats=False)
    data = MyCSVData(
        dataname='TQBR.SBER_D1.txt',
        separator=',',
        fromdate=datetime(2024, 1, 1),
        todate=datetime(2026, 1, 1)
    )
    cerebro.adddata(data)
    cerebro.addstrategy(TestStrategy)
    cerebro.run()
    print('✅ Данные успешно загружены и обработаны!')
