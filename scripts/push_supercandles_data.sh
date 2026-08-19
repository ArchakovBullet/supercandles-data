#!/bin/bash
cd /root/finlab/data/supercandles
git remote set-url origin https://github.com/ArchakovBullet/supercandles-data.git 2>/dev/null
git config user.email "archakov@finlab.ru"
git config user.name "FinLabPy Bot"
git add *.parquet
git commit -m "Daily update $(date +%Y-%m-%d)" 2>/dev/null || echo "No changes"
git push origin master 2>&1
echo "[$(date)] Push completed"
