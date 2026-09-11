"""
Единый модуль логирования для FinLabPy
Все логи сохраняются в E:\Python\FinLabProject\logs\
"""
import logging
import sys
from datetime import datetime
from pathlib import Path

def setup_logger(name: str, level: str = "INFO") -> logging.Logger:
    """
    Создает настроенный логгер
    
    Args:
        name: Имя логгера (обычно __name__)
        level: Уровень логирования (DEBUG, INFO, WARNING, ERROR)
    
    Returns:
        Настроенный логгер
    """
    # Создаем папку logs в корне проекта
    project_root = Path(__file__).parent.parent.parent
    # На сервере используем /root/finlab/logs, локально - E:\Python\FinLabProject\logs
    if project_root.exists() and str(project_root).startswith('/'):
        logs_dir = Path('/root/finlab/logs')
    else:
        logs_dir = project_root / 'logs'
    logs_dir.mkdir(exist_ok=True)
    
    # Имя файла: YYYY-MM-DD_name.log
    date_str = datetime.now().strftime("%Y-%m-%d")
    log_file = logs_dir / f"{date_str}_{name.split('.')[-1]}.log"
    
    # Настраиваем логгер
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))
    
    # Обработчик для файла
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(funcName)-20s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    
    # Обработчик для консоли
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        '%(levelname)-8s | %(message)s'
    )
    console_handler.setFormatter(console_formatter)
    
    # Добавляем обработчики (избегаем дублирования)
    if not logger.handlers:
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
    
    return logger

def get_logger(name: str) -> logging.Logger:
    """Получить существующий или создать новый логгер"""
    return logging.getLogger(name) or setup_logger(name)

def cleanup_old_logs(days: int = 30):
    """Удаляет логи старше указанного количества дней"""
    project_root = Path(__file__).parent.parent.parent
    logs_dir = project_root / "logs"
    
    if not logs_dir.exists():
        return
    
    import time
    cutoff = time.time() - (days * 24 * 60 * 60)
    
    for log_file in logs_dir.glob("*.log"):
        if log_file.stat().st_mtime < cutoff:
            log_file.unlink()
            print(f"🗑️ Удален старый лог: {log_file.name}")
