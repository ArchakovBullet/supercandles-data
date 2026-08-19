#!/bin/bash
# Очистка старых данных. Оставляет только последние N дней.
# Все данные уже синхронизированы с GitHub.

DATA_DIR="/root/finlab/data"
LOG_FILE="/root/finlab/logs/cleanup_data.log"

echo "$(date): Начало очистки" >> $LOG_FILE

find $DATA_DIR/candles -name "*.parquet" -mtime +30 -delete -exec echo "$(date): Удалён {}" >> $LOG_FILE \;
find $DATA_DIR/tradestats -name "*.parquet" -mtime +30 -delete -exec echo "$(date): Удалён {}" >> $LOG_FILE \;
find $DATA_DIR/futoi -name "*.parquet" -mtime +5 -delete -exec echo "$(date): Удалён {}" >> $LOG_FILE \;
find $DATA_DIR/hi2 -name "*.parquet" -mtime +5 -delete -exec echo "$(date): Удалён {}" >> $LOG_FILE \;
find $DATA_DIR/funding -name "*.parquet" -mtime +30 -delete -exec echo "$(date): Удалён {}" >> $LOG_FILE \;
find $DATA_DIR/supercandles -name "*.parquet" -mtime +30 -delete -exec echo "$(date): Удалён {}" >> $LOG_FILE \;

echo "$(date): Очистка завершена" >> $LOG_FILE
