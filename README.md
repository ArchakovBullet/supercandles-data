# FinLabPy — Паспорт для AI-ассистента

**Актуально на:** 16.09.2026

---

## 0. Идеология проекта: подход Джима Саймонса

**FinLabPy — это количественная торговля в духе Renaissance Technologies.**

Мы опираемся на принципы **Джима Саймонса** — математика, основателя Renaissance Technologies (Medallion Fund: ~66% годовых, 30+ лет):

### Принципы

1. **Данные — прежде всего.**
   Каждое решение — на основе качественных, свежих данных.
   Свежесть критична: `is_tf_fresh`, `is_futoi_fresh`, `is_moex_trading_day`.
   **Никаких решений на устаревших данных.**

2. **Статистика, а не интуиция.**
   Win Rate, PnL, просадка, время удержания — **основа решений**.
   **Бэктесты** перед внедрением. **Никаких «мне кажется».**

3. **Системность и повторяемость.**
   Один алгоритм → один результат. **Никаких ручных вмешательств.**
   Робот работает **по правилам**, а не по настроению.

4. **Много маленьких ставок (диверсификация).**
   Много пар, много тикеров, много стратегий.
   **Риск на сделку — маленький, портфель — большой.**

5. **Контроль риска.**
   **Стопы** обязательны (сейчас — виртуальные, в бою — на бирже).
   **Лимиты позиций** (`MAX_POSITIONS`), **фильтры** (время, волатильность, FutOI).

6. **Постоянное улучшение.**
   Анализ **каждой сделки** (STOP/SIGNAL/SCORE_EXIT).
   Оптимизация параметров (Entry=2.0 → 3.0).
   Отказ от **убыточных тикеров** (CE, MG, NA).

7. **Наука, а не религия.**
   Гипотезы проверяются **экспериментально**.
   Если не работает — **отбрасываем**.
   **Никакой веры** в «магические» индикаторы.

### Практические следствия для проекта

- **Любая правка** — с обоснованием (статистика, бэктест)
- **Каждое решение** — документируется в `WORK_LOG.md`
- **Приоритет** — контроль риска и качество данных
- **При сомнениях** — консервативный выбор (меньше позиций, шире стопы, выше порог входа)

---


---

## 1. Доступы

- **Сервер:** `root@159.194.219.117` (Ubuntu 24.04, Python 3.12)
- **Рабочая директория:** `/root/finlab`
- **VS Code Server:** http://159.194.219.117:8080
- **Токены** — в `/root/finlab/.env`:
  - `MOEX_TOKEN`, `VK_TOKEN`, `VK_GROUP_ID`, `GITHUB_TOKEN`
  - `TINVEST_TOKEN`, `ALOR_TOKEN`
  - `REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt`

---

## 2. Критично

### MOEX TLS-сертификаты

С 21.08.2026 MOEX перешёл на сертификаты НУЦ Минцифры. Без установки корневого сертификата все запросы к MOEX API падают (HTTP 000).

Установка: bash /root/finlab/scripts/fix_moex_certs.sh

Проверка: curl -sS -o /dev/null -w "%{http_code}\n" https://iss.moex.com/iss/engines/stock/markets/shares/securities.json (ожидаем 200)

Важно: при обновлении certifi файл перезаписывается — сертификат надо установить снова.

### BOM (Byte Order Mark)

Файлы .py, созданные в Windows (PowerShell), содержат BOM (EF BB BF). Python 3.12 падает на ast.parse() при BOM.

Проверка:
python3 -c "from pathlib import Path; [print(f) for f in Path('/root/finlab').rglob('*.py') if 'venv' not in str(f) and open(f,'rb').read(3) == b'\xef\xbb\xbf']"

---

## 3. Структура проекта

/root/finlab/
  FinLabPy/ - основной код
    DataCollectors/ - сборщики (cron)
      tickers_config.json - stocks (138), futures (165)
      futoi_tickers_config.json - тикеры с FutOI
      contract_cache.json - короткий код → SECID
    My_Indicators/ - индикаторы, unified_scanner
      pairs_config.json - конфиг пар
    Strategies/, Utils/, Brokers/, MOEXPy/
  robots/ - торговые роботы
    pairs_robot.py + pairs_robot.db - парный
    futures_robot.py + futures_robot.db - фьючерсный
    contract_points.json - point_value (58 тикеров)
  finlab_dashboard/ - дашборд
    app_v2.py - Streamlit
  scripts/ - скрипты
    fix_moex_certs.sh
    build_contract_points.py
    check_contract_changes.py
  data/ - Parquet-хранилище
    candles/ - {ticker}_{tf}.parquet
    futoi/ - {ticker}_futoi.parquet
    futoi_1h/, futoi_4h/ - агрегаты
    hi2/, supercandles/
  backups/ - бэкапы
  .env
  README.md - этот файл
  WORK_LOG.md - дневник

---


### Контроль риска (Саймонс-подход)

**Лимит позиций:**
- `MAX_POSITIONS = 10` — максимум одновременных открытых позиций
- При достижении лимита — новые позиции не открываются

**Cooldown после убытка:**
- `COOLDOWN_HOURS = 4` — пауза после STOP/убытка
- Фьючерсный робот: после STOP по тикеру
- Парный робот: после убытка по паре
- Защита от whipsaw (повторных входов)

**Проверка стопов (фьючерсный):**
- `check_stops_only()` — каждые 10 минут
- По M10 (high/low) — реалистично
- Закрытие по `stop_price` (не по low/high)
- В неторговые дни — не работает (`is_moex_trading_day`)

**Календарь MOEX:**
- `is_moex_trading_day()` — учитывает выходные + исключения
- MOEX торгует в сб/вс (09:50–19:00), но есть неторговые (12–13.09, 3–4.01 и т.д.)

**Управление парами:**
- `enabled: true/false` — в `pairs_config.json`
- `pairs_robot.py` — читает `enabled`
- `pairs_optimizer.py` — сохраняет `enabled` при переоптимизации
- `weekly_pairs_optimization.py` — не возвращает отключённые (короткие) пары

---

## 4. Роботы

### Парный робот
- Файл: robots/pairs_robot.py
- Systemd: finlab-robot.service
- БД: robots/pairs_robot.db (таблица positions)
- Конфиг: FinLabPy/My_Indicators/pairs_config.json
- Таймфреймы: M10, H1, H4, D1
- Логика: z-score спреда, вход при |Z| > entry_z
- Свежесть: M10=2ч, H1=4ч, H4=12ч, D1=24ч
- Фильтры: время (07:00–18:00 МСК), волатильность
- Двухногая модель: leg_a_ticker, leg_b_ticker, leg_a_pnl, leg_b_pnl
- PnL: (exit − entry) × point_value × volume

### Робот фьючерсов
- Файл: robots/futures_robot.py
- Systemd: finlab-futures-robot.service
- БД: robots/futures_robot.db (таблица futures_positions)
- Логика: unified_scanner (1D + 4H + 1H, веса 50/30/20)
- Сигналы: `yur_buy_ratio` (16.09.2026) + HI2 (11 метрик) + TradeStats `disb`
- Вход: score ≥ 60 (или 80 в кризис)
- Стоп: **3.2×ATR + безубыток** (15.09.2026), проверка каждые 10 мин по M10
- Безубыток: при движении в плюс на 1.5×ATR → стоп в entry_price
- Выход: обратный сигнал / score < 40 / стоп / безубыток
- Свежесть: FutOI = 24ч
- Фильтры: время (10:00–18:00 МСК), FutOI, готовые агрегаты
- PnL: (exit − entry) × point_value × volume + `pnl_points`
- Проверка: каждый час (systemd, не cron) + стопы каждые 10 мин

---

## 5. Конфиги и данные

### Тикеры
- Данные хранятся под КОРОТКИМИ кодами: RI, LK, RN, CE, SMLT, SNGSP
- MOEX ISS — под ДЛИННЫМИ ASSETCODE: RTS, LKOH, ROSN, COPPER, GOLD
- Маппинг: contract_cache.json (LK → LKU6)

### contract_points.json
- Ключи — короткие коды (как в БД)
- Значения — point_value
- Фьючерсы: point_value = STEPPRICE × MINSTEP
- Акции: point_value = 1.0
- Вечные фьючерсы (CNYRUBF, SBERF, GAZPF): SECID = тикер
- Обновление: scripts/build_contract_points.py

### FutOI
- Сырые данные: data/futoi/{ticker}_futoi.parquet
- Готовые агрегаты: data/futoi_4h/futoi_4h.parquet, data/futoi_1h/futoi_1h.parquet
- Колонки: ticker, block/hour, fiz_buy_ratio, fiz_ratio_delta, yur_buy_ratio

### Сигналы (16.09.2026)

**`yur_buy_ratio` (юрлица) — рабочий сигнал:**
- D1: корреляция 0.27–0.51 (RI, SBERF, GZ, MG, SN, CE)
- H4: корреляция 0.30–0.51 (GD, SBERF, GZ, SN, CE)
- H1: слабее

**`fiz_buy_ratio` (физлица) — НЕ работает:**
- Корреляция ~0
- Использовать как контр-индикатор (10%)

**Конфиги:**
- `robots/signal_direction.json` — `dir`, `median`, `std` для 8 тикеров
- `robots/yur_stats.json` — статистика по 63 тикерам

**Стратегии:**
- **C+D** (основная): группы + динамические пороги
- **E** (тест): мультифакторная (yur_buy 30%, HI2 20%, disb 20%, GARCH 10%, тренд 10%, объём 10%)
- **A/B** (отложено): индивидуальные / единый

**Группы для C:**
- Индексы (RI, MX, ...)
- Акции (SBERF, GAZPF, LK, ...)
- Товары (SN, MG, GD, ...)
- Валюты (CNYRUBF, USDRUBF, ...)

---

## 6. Workflow

### Всё делается на сервере
- Локальная машина (Windows) НЕ используется
- Код редактируется через VS Code Remote SSH
- WORK_LOG ведётся на сервере

### Git
Код, данные, роботы: cd /root/finlab && git push origin master
Дашборд, дневник: cd /root/finlab && git push finlab-dashboard master

### Особенности
- WORK_LOG.md в .gitignore → git add -f WORK_LOG.md
- MOEXPy в .gitignore → git add -f FinLabPy/MOEXPy/MOEXPy/MOEXPy.py
- При конфликтах: git checkout --ours WORK_LOG.md

### Remote
- origin → supercandles-data (публичный)
- finlab-dashboard → finlab-dashboard

---

## 7. Правила работы с AI

- Обращение: Напарник
- Язык: код, комментарии, документация — русский
- Формат ответа:
  1. Проблема — что случилось
  2. Причина — почему
  3. Рекомендация — что делать
  4. Команды для терминала — готовые для копирования
  5. Ожидаемый результат — что должно быть
  6. Дальнейший план — следующий шаг
- При правках: бэкап → изменение → проверка синтаксиса → коммит

---

## 8. Полезные команды

Статус роботов: systemctl status finlab-robot.service finlab-futures-robot.service
Логи: journalctl -u finlab-futures-robot.service -n 30 --no-pager
Открытые (парный): sqlite3 /root/finlab/robots/pairs_robot.db "SELECT * FROM positions WHERE status='OPEN';"
Открытые (фьючерс): sqlite3 /root/finlab/robots/futures_robot.db "SELECT * FROM futures_positions WHERE status='OPEN';"
PnL (парный): sqlite3 /root/finlab/robots/pairs_robot.db "SELECT COUNT(*), ROUND(SUM(pnl),2) FROM positions WHERE status='CLOSED' AND (exit_price_a != 0 AND exit_price_b != 0);"
PnL (фьючерс): sqlite3 /root/finlab/robots/futures_robot.db "SELECT COUNT(*), ROUND(SUM(pnl),2) FROM futures_positions WHERE status='CLOSED';"
Свежесть: /root/finlab/venv/bin/python /root/finlab/FinLabPy/DataCollectors/check_data_freshness.py
Обновить contract_points: /root/finlab/venv/bin/python /root/finlab/scripts/build_contract_points.py
Cron: crontab -l

---

## 9. История

Дневник разработки: https://raw.githubusercontent.com/ArchakovBullet/supercandles-data/master/WORK_LOG.md

Все статусы задач, план на день, история изменений — в WORK_LOG.md.
