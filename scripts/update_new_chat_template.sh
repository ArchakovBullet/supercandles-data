#!/bin/bash
# Обновить шаблон для нового чата с актуальным commit hash
cd /root/finlab

# Обновить COMMIT_HASH.txt
git rev-parse --short HEAD > /root/finlab/COMMIT_HASH.txt
COMMIT=$(cat /root/finlab/COMMIT_HASH.txt)

# Создать шаблон
cat > /root/finlab/scripts/new_chat_template.txt << TEMPLATE
Привет, напарник! Продолжаем работу над FinLabPy.

Прочитай актуальный WORK_LOG и README (через commit hash, без кэша):

1. https://raw.githubusercontent.com/ArchakovBullet/supercandles-data/${COMMIT}/WORK_LOG.md
2. https://raw.githubusercontent.com/ArchakovBullet/supercandles-data/${COMMIT}/README.md

Проверь VERSION в первой строке WORK_LOG.md. Ожидаемый:
$(head -1 WORK_LOG.md)

Продолжаем работу! Твои ответы строго так:
1. Проблема — что случилось.
2. Рекомендация — что делать.
3. Команды для терминала — готовые для копирования.
4. Дальнейший план — следующий шаг.
5. Ожидаемый результат — что должно быть.
TEMPLATE

echo "✅ Шаблон обновлён: /root/finlab/scripts/new_chat_template.txt"
echo "   Commit: $COMMIT"
