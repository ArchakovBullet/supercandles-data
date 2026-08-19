#!/bin/bash
# Автопуш данных FutOI в GitHub

DATA_REPO="/root/futoi-data"
GITHUB_URL="https://${GITHUB_TOKEN}@github.com/ArchakovBullet/futoi-data.git"

cd "$DATA_REPO"

git remote set-url origin "$GITHUB_URL" 2>/dev/null
git config user.email "archakov@finlab.ru"
git config user.name "FinLabPy Bot"

cp /root/finlab/data/futoi_daily.parquet ./
mkdir -p futoi
cp /root/finlab/data/futoi/*.parquet futoi/ 2>/dev/null

git add .
git commit -m "Auto-update $(date +%Y-%m-%d_%H:%M)" 2>/dev/null || echo "Нет изменений"
git push origin main 2>&1

echo "[$(date)] Готово"
