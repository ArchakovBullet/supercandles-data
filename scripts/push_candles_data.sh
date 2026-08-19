#!/bin/bash
cd /root/finlab/data/candles
git add *.parquet
git commit -m "Update $(date +%Y-%m-%d_%H:%M)" 2>/dev/null
git push origin master 2>&1
echo "$(date): push completed"
