# Добавляем метод get_tradestats в конец класса MOEXPy (перед последней строкой)
    def get_tradestats(self, ticker, dt_from, dt_till, board='TQBR'):
        '''Super Candles: агрегированная статистика сделок

        param str ticker: Тикер акции
        param date dt_from: Дата начала
        param date dt_till: Дата окончания
        param str board: Режим торгов (TQBR для акций)
        '''
        # Определяем тип рынка по board
        if board == 'TQBR':
            market_code = 'eq'  # акции
        elif board == 'RFUD':
            market_code = 'fo'  # фьючерсы
        else:
            market_code = 'eq'
        
        url = f'{self.api_server}/datashop/algopack/{market_code}/tradestats/{ticker}.json'
        all_data = None
        cursor = 0
        
        while True:
            params = {
                'from': dt_from.strftime('%Y-%m-%d'),
                'till': dt_till.strftime('%Y-%m-%d'),
                'start': cursor
            }
            response = get(url, params=params, headers=self.headers)
            content = loads(response.content.decode('utf-8'))
            
            rows = content['data']['data']
            total = content['data.cursor']['data'][0][1]
            
            if all_data is None:
                all_data = content
            else:
                all_data['data']['data'].extend(rows)
            
            cursor += len(rows)
            if cursor >= total:
                break
        
        return all_data
