# 📋 СИСТЕМА ЛОГИРОВАНИЯ FinLabPy

## 📅 Настроено: 21.04.2026

## 🗂️ СТРУКТУРА ЛОГОВ

E:\Python\FinLabProject\
├── logs/                          # ЕДИНАЯ ПАПКА ЛОГОВ (в .gitignore)
│   └── YYYY-MM-DD_strategy.log    # Логи за конкретную дату
├── FinLabPy/
│   └── Utils/
│       ├── __init__.py
│       └── Logger.py              # Модуль логирования
└── .gitignore                     # logs/ добавлен в игнор

## 🔧 ИСПОЛЬЗОВАНИЕ В КОДЕ

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from FinLabPy.Utils import setup_logger

logger = setup_logger(__name__)
logger.info("Стратегия запущена")

## 🚫 ЧТО В .GITIGNORE

# Логи
logs/
*.log
log_*.txt
debug*.txt

**Статус:** ✅ Настроено и работает
