#!/bin/bash
CURRENT=$(crontab -l 2>/dev/null)
BACKUP=$(cat /root/finlab/infrastructure/crontab.txt)

# Проверяем количество задач
CURRENT_TASKS=$(echo "$CURRENT" | grep -c "finlab")
BACKUP_TASKS=$(echo "$BACKUP" | grep -c "finlab")

if [ "$CURRENT_TASKS" -lt "$BACKUP_TASKS" ]; then
    echo "⚠️ CRITICAL: crontab повреждён! Задач: $CURRENT_TASKS (должно быть $BACKUP_TASKS)"
    echo "Восстанавливаю из бэкапа..."
    crontab /root/finlab/infrastructure/crontab.txt
    echo "✅ crontab восстановлен"
fi
