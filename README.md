# FinLabPy — Паспорт для AI-ассистента

**Актуально на:** 23.09.2026
## ВАЖНО: Кэш GitHub raw — инструкция для AI

raw.githubusercontent.com КЭШИРУЕТСЯ до 5-10 минут.
Если ты читаешь WORK_LOG — используй один из способов:

Способ 1: URL с timestamp — добавь ?t=<unixtime> в конец URL.
Способ 2: GitHub API — api.github.com/repos/ArchakovBullet/supercandles-data/contents/WORK_LOG.md?ref=master

Проверка актуальности: первая строка WORK_LOG.md — VERSION-маркер.
Если VERSION старше 24 часов — читаешь из кэша.

Автообновление VERSION: python3 /root/finlab/scripts/update_worklog_version.py

---

## 0. Идеология проекта: подход Джима Саймонса

**FinLabPy — это количественная торговля в духе Renaissance Technologies.**

Мы опираемся на принципы **Джима Саймонса** — математика, основателя Renaissance Technologies (Medallion Fund: ~66% годовых, 30+ лет):

1. **Данные — прежде всего.**
   Свежесть критична: is_tf_fresh, is_futoi_fresh, is_moex_trading_day.

2. **Статистика, а не интуиция.**
   Win Rate, PnL, просадка — основа решений. Бэктесты перед внедрением.

3. **Системность и повторяемость.**
   Один алгоритм - один результат. Никаких ручных вмешательств.

4. **Много маленьких ставок (диверсификация).**
   Много пар, тикеров, стратегий. Риск на сделку маленький.

5. **Контроль риска.**
   Стопы обязательны. Лимиты позиций. Фильтры (время, волатильность).

6. **Постоянное улучшение.**
   Анализ каждой сделки. Оптимизация параметров.

7. **Наука, а не религия.**
   Гипотезы проверяются экспериментально. Если не работает - отбрасываем.

## 1. Доступы

- Сервер: root@159.194.219.117 (Ubuntu 24.04, Python 3.12)
- Рабочая директория: /root/finlab
- VS Code Server: http://159.194.219.117:8080
- Токены: /root/finlab/.env

## 2. Критично

### MOEX TLS-сертификаты
Установка: bash /root/finlab/scripts/fix_moex_certs.sh

### BOM (Byte Order Mark)
Файлы .py из Windows содержат BOM. Python 3.12 падает на ast.parse().

## 3. Структура проекта

/root/finlab/
  FinLabPy/
    DataCollectors/ - сборщики (cron)
    My_Indicators/ - индикаторы
      stock_screener.py       # Скринер акций
      stock_scanner_tf.py     # Вердикт D1+H1+M10
      garch_indicator.py      # GARCH(1,1)
      arms_index.py           # TRIN
      market_regime.py        # Режим рынка
      trading_session.py      # Сессия
      zweig_filter.py         # Zweig
      sector_analysis.py      # Сектор
      unified_scanner.py      # Сканер фьючерсов
    Strategies/, Utils/, Brokers/, MOEXPy/
  robots/
    pairs_robot.py + pairs_robot.db          # Парный
    futures_robot.py + futures_robot.db      # Фьючерсный
    stocks_robot.py + stocks_robot.db        # Акций (NEW 21.09)
    stock_to_sector.json                     # Сектора акций
    stop_config.json                         # Индивидуальные стопы
  finlab_dashboard/
    app_v2.py - Streamlit
  scripts/
    fix_moex_certs.sh
    build_stock_to_sector.py
    backtest_stop_levels.py
  data/
    candles/ - D1/H1/M10/H4
    futoi/, futoi_1h/, futoi_4h/
    hi2/, hi2_daily.parquet
    sector_indices/ - 10 отраслевых индексов MOEX
  .env
  README.md
  WORK_LOG.md

## 4. Роботы (3 штуки)

### Парный робот
- Файл: robots/pairs_robot.py
- Systemd: finlab-robot.service
- БД: robots/pairs_robot.db
- Логика: z-score спреда
- Запрет шорта по акциям (is_stock)
- MAX_POSITIONS: 10
- Cooldown: 4ч

### Робот фьючерсов
- Файл: robots/futures_robot.py
- Systemd: finlab-futures-robot.service
- БД: robots/futures_robot.db
- Логика: unified_scanner (1D+4H+1H)
- Вход: score >= 60 (или 80 в кризис)
- Стоп: 3.2xATR (индивидуальный: RI/MG/GZ/MC = 2.5) + безубыток x1.001

### Робот акций (NEW - 21.09.2026)
- Файл: robots/stocks_robot.py
- Systemd: finlab-stocks-robot.service
- БД: robots/stocks_robot.db
- Логика: get_stock_scanner_verdict (D1+H1+M10)
- Только LONG
- Вход: score >= 60 (70 при CAUTION)
- Стоп: 3.2xATR + безубыток x1.001
- Тикеры: stocks[:50] (49 с данными)
- MAX_POSITIONS: 10
- Проверка: раз в час

## 5. Сектора акций

- Файл: robots/stock_to_sector.json
- Источник: MOEX ISS
- 10 отраслевых индексов
- 104 тикера, stocks[:50] - 100%
- Скрипт: scripts/build_stock_to_sector.py

## 6. Workflow

- Всё на сервере, VS Code Remote SSH
- Git: git push origin master, git push finlab-dashboard master
- WORK_LOG в .gitignore -> git add -f WORK_LOG.md

## 7. Правила работы с AI

- Обращение: Напарник
- Формат: 1) Проблема, 2) Причина, 3) Рекомендация, 4) Команды, 5) Ожидаемый результат, 6) План
- При правках: бэкап -> изменение -> проверка синтаксиса -> коммит

## 8. Полезные команды

# Статус роботов
systemctl status finlab-robot.service finlab-futures-robot.service finlab-stocks-robot.service

# Логи
journalctl -u finlab-stocks-robot.service -n 30 --no-pager
tail -30 /root/finlab/robots/stocks_robot.log

# Открытые позиции
sqlite3 /root/finlab/robots/stocks_robot.db "SELECT * FROM stock_positions WHERE status='OPEN';"

# Свежесть данных
/root/finlab/venv/bin/python /root/finlab/FinLabPy/DataCollectors/check_data_freshness.py

## 9. История

- 13.09-15.09 — Стопы, cooldown, rollover.
- 16.09 — yur_buy_ratio, TradeStats, HI2.
- 17.09 — Rollover, фильтр корреляции.
- 18.09 — Защита от экспирации.
- 19.09 — Cooldown, M10 каждые 10 мин, RI 2.5xATR.
- 20.09 — is_moex_trading_day (сб/вс), индивидуальные стопы, запрет шорта по акциям.
- 21.09 — exit_reason, abs(_corr), Робот акций, stock_to_sector.json, дашборд.
- 22.09 — Сводка состояния.

## 10. Открытые задачи

Приоритет 1:
- [ ] Merge FutOI (fiz_delta=0, D1 fiz_buy=50)
- [ ] A/B тест сигналов

Приоритет 2:
- [ ] Проверить робота акций в проде
- [ ] Переделать backtest_stop_levels.py
- [ ] Walk-forward оптимизация пар

Приоритет 3:
- [ ] use_container_width -> width='stretch'
- [ ] Проверить 14 FAIL-пар
- [ ] Cron для build_stock_to_sector.py
