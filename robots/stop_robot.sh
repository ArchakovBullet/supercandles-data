#!/bin/bash
# Остановка робота с закрытием позиций
echo "STOP" > /root/finlab/robots/robot_command.txt
sleep 3
if [ -f /root/finlab/robots/robot.pid ]; then
    PID=$(cat /root/finlab/robots/robot.pid)
    kill $PID 2>/dev/null
    rm -f /root/finlab/robots/robot.pid
    echo "✅ Робот остановлен (PID: $PID)"
else
    echo "⚠️ PID-файл не найден"
fi
