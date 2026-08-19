#!/bin/bash
cd /root/finlab/data/tradestats
git add *.parquet
git commit -m "Update $(date +%Y-%m-%d_%H:%M)" 2>/dev/null
git push origin master 2>&1
echo "$(date): push completed"
