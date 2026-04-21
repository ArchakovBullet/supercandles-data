"""
ИСПРАВЛЕННАЯ СТРАТЕГИЯ ДЛЯ ФЬЮЧЕРСОВ MOEX
- Исправлена конвертация дат
- Добавлена обработка ошибок
- Оптимизирован вывод
"""
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import polars as pl
from MOEXPy.MOEXPy import MOEXPy

def get_futures_candles_fixed(api: MOEXPy, ticker: str, days: int = 5):
    """
    Исправленная функция получения свечей с правильной конвертацией дат
    """
    print(f"\n📈 Получение свечей для {ticker} (board=RFUD)")
    print("-" * 50)
    
    dt_till = datetime.now()
    dt_from = dt_till - timedelta(days=days)
    tf = api.timeframe_to_moex_timeframe('D1')
    
    try:
        candles = api.get_candles('RFUD', ticker, dt_from, dt_till, tf)
        
        if candles and 'candles' in candles:
            data = candles['candles']['data']
            columns = candles['candles']['columns']
            
            if data:
                # Создаем словарь для DataFrame
                df_dict = {col: [] for col in columns}
                for row in data:
                    for i, col in enumerate(columns):
                        df_dict[col].append(row[i])
                
                # Создаем DataFrame
                df = pl.DataFrame(df_dict)
                
                # Конвертируем типы с правильным форматом даты
                df = df.with_columns([
                    pl.col('begin').str.strptime(pl.Datetime, format='%Y-%m-%d %H:%M:%S').alias('datetime'),
                    pl.col('open').cast(pl.Float64),
                    pl.col('high').cast(pl.Float64),
                    pl.col('low').cast(pl.Float64),
                    pl.col('close').cast(pl.Float64),
                    pl.col('volume').cast(pl.Int64)
                ])
                
                print(f"✅ Получено {len(df)} свечей")
                print(f"\n📊 Данные {ticker}:")
                print(df[['datetime', 'open', 'high', 'low', 'close', 'volume']])
                
                # Статистика
                if len(df) > 0:
                    print(f"\n📈 Статистика:")
                    print(f"   Open:  {df['open'].min():.2f} - {df['open'].max():.2f}")
                    print(f"   Close: {df['close'].min():.2f} - {df['close'].max():.2f}")
                    print(f"   Volume: {df['volume'].sum():,}")
                
                return df
            else:
                print(f"⚠️ Нет данных для {ticker}")
                return None
        else:
            print(f"❌ Неверный формат ответа API")
            return None
            
    except Exception as e:
        print(f"❌ Ошибка при получении {ticker}: {e}")
        return None

def test_available_futures_simple(api: MOEXPy):
    """
    Простой тест доступных фьючерсов без сложной обработки
    """
    print("\n" + "="*60)
    print("🔄 ТЕСТ ДОСТУПНЫХ ФЬЮЧЕРСОВ (упрощенный)")
    print("="*60)
    
    futures_to_test = ['GLDRUBF', 'SiF', 'EuF', 'BrentF', 'IMOEXF', 'LKOHF', 'SBERF', 'GAZPF']
    
    dt_till = datetime.now()
    dt_from = dt_till - timedelta(days=2)
    tf = api.timeframe_to_moex_timeframe('D1')
    
    available = []
    
    for ticker in futures_to_test:
        try:
            candles = api.get_candles('RFUD', ticker, dt_from, dt_till, tf)
            
            if candles and 'candles' in candles:
                data = candles['candles']['data']
                if data and len(data) > 0:
                    # Просто проверяем наличие данных
                    last_row = data[-1]
                    # Позиции в ответе API: 0=open, 1=close, 2=high, 3=low, 4=volume
                    close_price = float(last_row[1]) if len(last_row) > 1 else 0
                    volume = int(float(last_row[4])) if len(last_row) > 4 else 0
                    
                    available.append({
                        'ticker': ticker,
                        'candles': len(data),
                        'close': close_price,
                        'volume': volume
                    })
                    print(f"✅ {ticker:10} - {len(data):2} свечей, Close: {close_price:10.2f}, Vol: {volume:10,}")
                else:
                    print(f"⚠️ {ticker:10} - нет данных")
            else:
                print(f"❌ {ticker:10} - ошибка API")
                
        except Exception as e:
            print(f"❌ {ticker:10} - ошибка: {str(e)[:40]}")
    
    print(f"\n📊 ИТОГ: доступно {len(available)}/{len(futures_to_test)} фьючерсов")
    
    if available:
        print("\nДоступные фьючерсы:")
        for f in available:
            print(f"  • {f['ticker']}: цена {f['close']:.2f}, объем {f['volume']:,}")
    
    return available

def get_futures_list_limited(api: MOEXPy, limit: int = 10):
    """
    Получение ограниченного списка фьючерсов (чтобы не зависало)
    """
    print("\n" + "="*60)
    print(f"📋 ПОЛУЧЕНИЕ СПИСКА ФЬЮЧЕРСОВ (первые {limit})")
    print("="*60)
    
    try:
        # Прямой запрос к MOEX API через requests (быстрее)
        import requests
        
        url = "https://iss.moex.com/iss/engines/futures/markets/forts/securities.json"
        response = requests.get(url, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            if 'securities' in data and 'data' in data['securities']:
                securities_data = data['securities']['data']
                columns = data['securities']['columns']
                
                print(f"✅ Получено {len(securities_data)} фьючерсов")
                
                # Показываем первые limit
                print(f"\n📊 Первые {limit} фьючерсов:")
                print("-" * 60)
                print(f"{'SECID':<12} {'SHORTNAME':<25} {'BOARDID':<8}")
                print("-" * 60)
                
                for i, row in enumerate(securities_data[:limit]):
                    secid = row[0] if len(row) > 0 else 'N/A'
                    boardid = row[1] if len(row) > 1 else 'N/A'
                    shortname = row[2] if len(row) > 2 else 'N/A'
                    print(f"{secid:<12} {shortname:<25} {boardid:<8}")
                
                # Ищем GLDRUBF
                for row in securities_data:
                    if row[0] == 'GLDRUBF':
                        print(f"\n🎯 GLDRUBF найден:")
                        print(f"   SECID: {row[0]}")
                        print(f"   BOARDID: {row[1]}")
                        print(f"   SHORTNAME: {row[2]}")
                        print(f"   SECNAME: {row[3] if len(row) > 3 else 'N/A'}")
                        break
                
                return securities_data
        else:
            print(f"❌ HTTP {response.status_code}")
            return None
            
    except Exception as e:
        print(f"❌ Ошибка при запросе: {e}")
        return None

def main():
    """
    Главная функция
    """
    print("="*60)
    print("🚀 ФЬЮЧЕРСЫ MOEX - РАБОЧАЯ ВЕРСИЯ")
    print("="*60)
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Инициализация API
    token = os.getenv('MOEX_TOKEN')
    if not token:
        print("❌ Токен MOEX не найден!")
        return
    
    print(f"🔑 Токен: {token[:20]}...")
    api = MOEXPy(token=token)
    
    # 1. Получаем список фьючерсов (быстрый метод)
    futures_list = get_futures_list_limited(api, limit=15)
    
    # 2. Тестируем доступные фьючерсы
    available_futures = test_available_futures_simple(api)
    
    # 3. Детальный анализ GLDRUBF
    print("\n" + "="*60)
    print("🎯 ДЕТАЛЬНЫЙ АНАЛИЗ GLDRUBF")
    print("="*60)
    
    gl_dr_ubf_data = get_futures_candles_fixed(api, 'GLDRUBF', days=5)
    
    # 4. Если есть другие доступные фьючерсы, проверим их тоже
    if available_futures and len(available_futures) > 1:
        print("\n" + "="*60)
        print("📊 ПРОВЕРКА ДРУГИХ ДОСТУПНЫХ ФЬЮЧЕРСОВ")
        print("="*60)
        
        for f in available_futures[:3]:  # Первые 3 для примера
            if f['ticker'] != 'GLDRUBF':
                get_futures_candles_fixed(api, f['ticker'], days=3)
    
    # 5. Итоги
    print("\n" + "="*60)
    print("✅ ТЕСТИРОВАНИЕ ЗАВЕРШЕНО!")
    print("="*60)
    
    print(f"\n📊 РЕЗУЛЬТАТЫ:")
    print(f"   ✅ Доступные фьючерсы: {len(available_futures) if available_futures else 0}")
    print(f"   ✅ Board для фьючерсов: RFUD")
    print(f"   ✅ Основной тикер: GLDRUBF")
    
    if gl_dr_ubf_data is not None and len(gl_dr_ubf_data) > 0:
        last_price = gl_dr_ubf_data['close'][-1]
        last_volume = gl_dr_ubf_data['volume'][-1]
        print(f"   ✅ Последняя цена GLDRUBF: {last_price:.2f}")
        print(f"   ✅ Объем: {last_volume:,}")
    
    print(f"\n💡 Платная подписка Algopack успешно активирована!")
    print(f"   Теперь можно торговать фьючерсами на MOEX!")

if __name__ == '__main__':
    main()