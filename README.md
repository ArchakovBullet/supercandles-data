# FinLabPy — Паспорт для AI-ассистента

**Актуально на:** 11.09.2026

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
- Вход: score ≥ 60 (или 80 в кризис)
- Выход: обратный сигнал / score < 40 / стоп 2×ATR
- Свежесть: FutOI = 24ч
- Фильтры: время (10:00–18:00 МСК), FutOI, готовые агрегаты
- PnL: (exit − entry) × point_value × volume
- Проверка: каждый час (systemd, не cron)

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
- Колонки: ticker, block/hour, fiz_buy_ratio, fiz_ratio_delta

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
