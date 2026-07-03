# 📋 ПАСПОРТ FinLabPy — ДЛЯ AI-АССИСТЕНТА

## 📅 Актуально на: 02.07.2026

---

## 🔗 ДОСТУПЫ

- **Локально:** E:\Python\FinLabProject (Windows, Python 3.12, venv)
- **Сервер:** root@159.194.219.117 (Ubuntu 24.04, Python 3.12, venv: /root/finlab/venv)
- **VS Code Server:** http://159.194.219.117:8080
- **Токены:** MOEX_TOKEN, TINVEST_TOKEN, ALOR_TOKEN

---

## 🚨 ПРАВИЛА РАБОТЫ (ИЗ RULES.MD)

- **Обращение:** Напарник
- **Язык:** весь код, комментарии, документация — строго на РУССКОМ
- **Данные:** polars основная библиотека, pandas только для backtrader
- **Логирование:** FinLabPy.Utils.setup_logger
- **Новый сборщик:** код + cron + check_collectors_health.py + vk_bot.py + запись в дневник
- **Код:** все изменения локально через PowerShell, сервер только pull и диагностика

---

## 🚨 GIT WORKFLOW

- **Код (FinLabPy):** локально -> git push -> сервер git pull
- **Дашборд (finlab-dashboard):** только на сервере /root/finlab/finlab_dashboard/app_v2.py
- **Дневник (finlab-diary):** локально -> git push из E:\Python\FinLabProjectinlab-diary
- **ЗАПРЕЩЕНО:** редактировать код на сервере
- **Рассинхрон:** git fetch origin master && git reset --hard origin/master

---

## 📦 API MOEXPy (Algopack)

Фьючерсы:
  candles = api.get_candles('RFUD', 'GLDRUBF', dt_from, dt_till, tf)
  futoi = api.get_futoi('GLDRUBF', dt_from, dt_till)

Акции:
  candles = api.get_candles('TQBR', 'SBER', dt_from, dt_till, 'D')
  trades = api.get_trades('TQBR', 'SBER', tradeno=None)
  hi2 = api.get_hi2('stocks', 'SBER', date)

Вечные фьючерсы: GLDRUBF, IMOEXF, SBERF, GAZPF, CNYRUBF, USDRUBF, EURRUBF
Срочные фьючерсы (короткий -> полный): BR->BRN6, SI->SIM6, GD->GDU6, RI->RIU6, MX->MXU6, ED->EDU6

---

## ⚠️ КРИТИЧЕСКИЕ ОСОБЕННОСТИ

- FutOI: pos_short с минусом -> abs(), clgroup='FIZ'/'YUR', API отдаёт 3-4 дня
- Свечи акций: MOEX отдаёт только M10, нет D1
- HI2: engine='stocks' (не 'stock'!)

---

## 📁 СТРУКТУРА ПРОЕКТА (сервер)

/root/finlab/
  FinLabPy/
    DataCollectors/    # Сборщики (cron)
    My_Indicators/     # Индикаторы
    Strategies/        # Стратегии
    Utils/             # Утилиты
  finlab_dashboard/
    app_v2.py          # Дашборд
  data/                # Parquet-хранилище
  RULES.md             # Правила для AI-ассистента
  vk_bot.py            # VK-бот

---

## 📊 ТЕКУЩИЙ СТАТУС (02.07.2026)

### Что работает:
- FutOI сборщик — вечные фьючерсы, cron каждый час
- HI2, Super Candles, Funding, TradeStats сборщики
- Дашборд v3.2: сканер, MegaAlerts, Zweig Filter, TRIN, HPI

### В процессе:
- Унификация тикеров для срочных фьючерсов (GD, BR, SI)
- Автозапуск FutOI при добавлении тикера

### Проблемы:
- Срочные фьючерсы не имеют данных FutOI
- README был повреждён -> восстановлен 02.07.2026

## 🗂️ НАВИГАЦИЯ ПО ДНЕВНИКУ

| 07.05 | WORK_LOG_2026-05-07.md | Проверка FutOI, начало акций |
| 08.05 | WORK_LOG_2026-05-08.md | HI2 сборщик, HMM прорыв |
| 01.07 | WORK_LOG_2026-07-01_ticker-debug.md | Отладка GD, проблема срочных фьючерсов |
