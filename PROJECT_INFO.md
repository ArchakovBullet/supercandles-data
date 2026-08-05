# FinLabPy — Ключевая информация

## Сервер
- Адрес: lvkseaqdin (159.194.219.117)
- Дашборд: http://159.194.219.117:8501
- Код: /root/finlab/FinLabPy
- Дашборд: /root/finlab/finlab_dashboard/app_v2.py
- Данные: /root/finlab/data/
- Логи: /root/finlab/logs/
- Python: /root/finlab/venv/bin/python
- PYTHONPATH: /root/finlab/FinLabPy

## Структура данных
- candles/ — свечи (M10, H1, D1, H4)
- futoi/ — открытые позиции физ/юр лиц
- hi2/ — индекс концентрации
- supercandles/ — Super Candles (акции)
- supercandles_h4/ — H4 агрегация Super Candles
- sector_indices/ — индексы секторов MOEX
- tradestats/ — обезличенные сделки
- funding/ — ставки фондирования

## Сборщики (DataCollectors/)
| Файл | Крон | Что собирает |
|------|------|-------------|
| candles_collector.py | 7-20 UTC ежечасно | M10, H1, D1 для акций и фьючерсов |
| futoi_collector.py | 7-20 UTC ежечасно | FutOI (только короткие коды!) |
| hi2_collector.py | 18:00 UTC ежедневно | HI2 (акции + фьючерсы, длинные коды) |
| supercandles_collector.py | 7-20 UTC ежечасно | Super Candles (акции) |
| supercandles_h4_aggregator.py | 17:40 UTC | H4 из Super Candles (акции) |
| futures_h4_aggregator.py | 17:45 UTC | H4 из M10 (фьючерсы) |
| sector_indices_collector.py | 19:00 UTC | Индексы MOEX |
| tradestats_collector.py | 18:30 UTC | TradeStats (вечные фьючерсы + акции) |
| funding_collector.py | 18:15 UTC | Ставки фондирования |

## Конфигурация тикеров
- Файл: DataCollectors/tickers_config.json
- stocks: AFLT, SBER, GAZP, GMKN, LKOH, HYDR, IRAO, PLZL, ROSN, TATN, VTBR, AFKS, T, YDEX, RUAL
- futures (вечные): CNYRUBF, USDRUBF, EURRUBF, GAZPF, GLDRUBF, IMOEXF, SBERF
- futures (срочные): BR, CE, CR, ED, FF, GD, MX, OJ, PD, PT, RI, SI, SV, VI, W4

## Формат тикеров для API
- FutOI: короткие коды (BR, SI, PT, VI...) — для всех фьючерсов
- HI2 stocks: короткие (SBER, GAZP...)
- HI2 futures: длинные коды через _resolve_full_code (BRU6, SiU6...)
- Свечи: длинные коды через get_full_code() для фьючерсов, короткие для акций
- TradeStats: только вечные фьючерсы и акции (срочные не поддерживаются)

## Известные проблемы
- MOEXTL: приостановлен с 20.03.2026 (мало эмитентов)
- TradeStats: не работает для срочных фьючерсов (письмо в Algopack)
- GN, SA: удалены из конфига (нет данных FutOI)

## Контакты поддержки
- Algopack API: algopack@moex.com
- MOEX API: iss.moex.com

## Git remotes
- Сервер: https://github.com/ArchakovBullet/supercandles-data.git (finlab)
- Локально: https://github.com/ArchakovBullet/finlab-dashboard.git (origin)
