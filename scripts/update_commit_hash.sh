#!/bin/bash
# Обновить COMMIT_HASH.txt текущим коротким хешем HEAD
cd /root/finlab
git rev-parse --short HEAD > /root/finlab/COMMIT_HASH.txt
echo "✅ COMMIT_HASH.txt обновлён: $(cat /root/finlab/COMMIT_HASH.txt)"
