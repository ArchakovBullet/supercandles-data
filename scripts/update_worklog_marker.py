#!/usr/bin/env python3
"""Обновить маркер версии в WORK_LOG.md (актуальная дата + коммит)."""
import re
import subprocess
from pathlib import Path
from datetime import datetime

WORKLOG = Path('/root/finlab/WORK_LOG.md')

# Получаем последний коммит
try:
    commit = subprocess.check_output(
        ['git', '-C', '/root/finlab', 'rev-parse', '--short', 'HEAD'],
        text=True
    ).strip()
except Exception:
    commit = 'unknown'

now = datetime.now().strftime('%Y-%m-%d %H:%M MSK')
new_marker = f'<!-- VERSION: {now} | COMMIT: {commit} -->'

text = WORKLOG.read_text(encoding='utf-8')
pattern = r'<!-- VERSION: \d{4}-\d{2}-\d{2} \d{2}:\d{2} MSK \| COMMIT: [a-f0-9]+ -->'

if re.search(pattern, text):
    text = re.sub(pattern, new_marker, text, count=1)
    print(f'✅ Маркер обновлён: {new_marker}')
else:
    text = new_marker + '\n' + text
    print(f'✅ Маркер добавлен: {new_marker}')

WORKLOG.write_text(text, encoding='utf-8')
