# ПАСПОРТ FinLabPy — ДЛЯ AI-АССИСТЕНТА

## Актуально на: 03.08.2026

---

## ДОСТУПЫ

- Локально: E:\Python\FinLabProject (Windows, Python 3.12, venv)
- Сервер: root@159.194.219.117 (Ubuntu 24.04, Python 3.12)
- VS Code Server: http://159.194.219.117:8080
- Токены: MOEX_TOKEN, TINVEST_TOKEN, ALOR_TOKEN

---

## ИДЕОЛОГИЯ: ДЖИМ САЙМОНС / RENAISSANCE TECHNOLOGIES

- Данные превыше всего
- Математика, не фундамент
- Скрытые закономерности
- Сначала исследование, потом роботы
- Портфельный подход

---

## СТАТУС ЗАДАЧ (актуально на 03.08.2026)

### ВЫПОЛНЕНО (июль-август)
- [x] Кризисный режим: сканер фьючерсов (GARCH>35%, RVI>70)
- [x] Кризисный режим: скринер акций (GARCH>35%, TRIN<0.5/>1.5)
- [x] RVI в дашборде
- [x] Volume Spike в unified_scanner и stock_scanner_tf
- [x] HI2-штраф унифицирован
- [x] _find_active_contract с сортировкой по экспирации
- [x] Блокировка тикеров без FutOI
- [x] Сборщик TRIN (cron)
- [x] Сборщик LQDT (бенчмарк)
- [x] Единый конфиг tickers_config.json
- [x] Все сборщики читают тикеры из конфига
- [x] Унификация списков акций в дашборде
- [x] YDEX заменён (YNDX делистингован)
- [x] Восстановлены срочные фьючерсы (19 тикеров)
- [x] HI2 для всех 14 акций
- [x] "ВЕРДИКТ НЕ АКТУАЛЕН" в дашборде при отсутствии данных
- [x] Подсветка устаревших данных в статусе сборщиков
- [x] Мониторинг свежести данных (check_data_freshness.py)
- [x] Суббота — торговая сессия (исправлено)
- [x] RVI восстановлен (sector_indices_collector.py)
- [x] FutOI 4H восстановлен
- [x] HI2 для акций — пометка "устаревшие" (ограничение MOEX API)

### ОСТАЛОСЬ (по приоритетам)
- [ ] Настроить VK-токены для уведомлений
- [ ] Кнопка "Добавить" — обновлять tickers_config.json (а не hi2_collector.py)
- [ ] Бэктест вердиктов — внедрить улучшения
- [ ] ML-модели
- [ ] Светофор рисков

---

## WORK_LOG

Актуальный дневник разработки: [WORK_LOG.md](https://raw.githubusercontent.com/ArchakovBullet/supercandles-data/master/WORK_LOG.md)

---

## ПРАВИЛА РАБОТЫ

- Обращение: Напарник
- Язык: весь код, комментарии, документация — строго на РУССКОМ
- Код (FinLabPy): локально -> git push -> сервер git pull
- Дашборд: сервер -> git push -> локально git pull
- ЗАПРЕЩЕНО: редактировать код на сервере
- WORK_LOG обновляется локально и пушится в GitHub при каждом изменении

---

## СТРУКТУРА ПРОЕКТА (сервер)

/root/finlab/
  FinLabPy/
    DataCollectors/    # Сборщики (cron)
    My_Indicators/     # Индикаторы
    Strategies/        # Стратегии
    Utils/             # Утилиты
  finlab_dashboard/
    app_v2.py          # Дашборд
  data/                # Parquet-хранилище
  vk_bot.py            # VK-бот


---

## ВАЖНО: Workflow (с 06.09.2026)

### Работа ведётся ТОЛЬКО на сервере

Сервер: lvkseaqdin (root), рабочая директория /root/finlab

### Как пушить изменения:

В репозиторий supercandles-data:
cd /root/finlab && git push origin master

В репозиторий finlab-dashboard:
cd /root/finlab && git push finlab-dashboard master

### Напоминания:
- WORK_LOG.md в .gitignore - использовать git add -f WORK_LOG.md
- MOEXPy в .gitignore - использовать git add -f FinLabPy/MOEXPy/MOEXPy/MOEXPy.py
- Дневник: /root/finlab/WORK_LOG.md (UTF-8, не UTF-16)

### Remote на сервере:
- origin - supercandles-data (данные, роботы, код)
- finlab-dashboard - finlab-dashboard (дашборд, дневник)

### Порядок работы с дневником:
1. Редактируем /root/finlab/WORK_LOG.md
2. git add -f WORK_LOG.md && git commit -m Update work log
3. git push origin master
4. git push finlab-dashboard master
