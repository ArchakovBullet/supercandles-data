"""
Скрипт автоматической очистки логов
Запуск: python cleanup_logs.py --days 7
"""

import os
import sys
import time
import argparse
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

def get_logs_dir():
    return Path(__file__).parent.parent.parent / "logs"

def get_dir_size(path: Path) -> float:
    total = 0
    if path.exists():
        for f in path.rglob('*'):
            if f.is_file():
                total += f.stat().st_size
    return total / (1024 * 1024)

def cleanup_by_age(logs_dir: Path, days: int, dry_run: bool = False):
    cutoff = datetime.now() - timedelta(days=days)
    deleted = 0
    size_freed = 0
    
    print(f"\n{'[DRY RUN] ' if dry_run else ''}Удаление логов старше {days} дней")
    print(f"Дата отсечки: {cutoff.strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 60)
    
    if not logs_dir.exists():
        print("Папка логов не найдена")
        return deleted, size_freed
    
    for log_file in logs_dir.rglob("*.log"):
        file_age = datetime.fromtimestamp(log_file.stat().st_mtime)
        if file_age < cutoff:
            file_size = log_file.stat().st_size
            size_freed += file_size
            if dry_run:
                print(f"  [БУДЕТ УДАЛЕН] {log_file.name} ({file_age.strftime('%Y-%m-%d')}, {file_size:,} B)")
            else:
                log_file.unlink()
                print(f"  🗑️ {log_file.name}")
            deleted += 1
    
    freed_mb = size_freed / (1024 * 1024)
    print(f"\n{'[DRY RUN] ' if dry_run else ''}Удалено: {deleted} файлов, {freed_mb:.2f} MB")
    return deleted, freed_mb

def main():
    parser = argparse.ArgumentParser(description='Очистка логов FinLabPy')
    parser.add_argument('--days', type=int, default=7, help='Удалить логи старше N дней (по умолчанию: 7)')
    parser.add_argument('--dry-run', action='store_true', help='Показать что будет удалено без реального удаления')
    parser.add_argument('--max-size', type=float, default=500, help='Макс. размер папки в MB (по умолчанию: 500)')
    
    args = parser.parse_args()
    logs_dir = get_logs_dir()
    
    print("=" * 60)
    print("🧹 ОЧИСТКА ЛОГОВ FinLabPy")
    print("=" * 60)
    print(f"Папка: {logs_dir}")
    print(f"Размер: {get_dir_size(logs_dir):.2f} MB")
    
    # Очистка по возрасту
    cleanup_by_age(logs_dir, args.days, args.dry_run)
    
    # Проверка размера
    current_size = get_dir_size(logs_dir)
    if current_size > args.max_size:
        print(f"\n⚠️ Размер папки ({current_size:.2f} MB) превышает лимит ({args.max_size} MB)")
        print(f"Запускаю принудительную очистку...")
        cleanup_by_age(logs_dir, max(1, args.days // 2), args.dry_run)
    
    print("=" * 60)
    print(f"✅ Готово. Размер: {get_dir_size(logs_dir):.2f} MB")
    print("=" * 60)

if __name__ == '__main__':
    main()
