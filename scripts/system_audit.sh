#!/bin/bash
ERRORS=0
MESSAGE="🔍 Ежедневный аудит системы:\n\n"

# Проверка crontab
if ! crontab -l | grep -q "futoi_collector.py"; then
    ERRORS=$((ERRORS+1))
    MESSAGE+="❌ FutOI collector отсутствует в crontab\n"
fi

if ! crontab -l | grep -q "candles_collector.py"; then
    ERRORS=$((ERRORS+1))
    MESSAGE+="❌ Candles collector отсутствует в crontab\n"
fi

# Проверка supervisor
if ! supervisorctl status vk_bot | grep -q RUNNING; then
    ERRORS=$((ERRORS+1))
    MESSAGE+="❌ VK bot не запущен\n"
fi

# Проверка свободного места
DISK_USAGE=$(df -h / | tail -1 | awk '{print $5}' | sed 's/%//')
if [ "$DISK_USAGE" -gt 90 ]; then
    ERRORS=$((ERRORS+1))
    MESSAGE+="⚠️ Диск заполнен на ${DISK_USAGE}%\n"
fi

if [ $ERRORS -eq 0 ]; then
    MESSAGE+="✅ Все системы в норме"
fi

echo -e "$MESSAGE"
