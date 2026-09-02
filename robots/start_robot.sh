#!/bin/bash
# Запуск робота парной торговли в фоне
cd /root/finlab
source .env
export PYTHONPATH=/root/finlab/FinLabPy
nohup /root/finlab/venv/bin/python -u /root/finlab/robots/pairs_robot.py > /root/finlab/robots/robot.log 2>&1 &
echo $! > /root/finlab/robots/robot.pid
echo "✅ Робот запущен (PID: $(cat /root/finlab/robots/robot.pid))"
