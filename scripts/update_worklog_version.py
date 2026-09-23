#!/usr/bin/env python3
"""Обновить VERSION-маркер в WORK_LOG.md. Вызывать перед git add."""
from pathlib import Path
from datetime import datetime
import subprocess

path = Path('/root/finlab/WORK_LOG.md')
content = path.read_text(encoding='utf-8')

lines = content.split('\n')
if lines and lines[0].startswith('<!-- VERSION'):
    lines = lines[1:]

try:
    commit = subprocess.check_output(['git', '-C', '/root/finlab', 'rev-parse', '--short', 'HEAD']).decode().strip()
except:
    commit = 'HEAD'

now = datetime.now().strftime('%Y-%m-%d %H:%M MSK')
version = f'<!-- VERSION: {now} | COMMIT: {commit} | LINES: {len(lines)} -->'

path.write_text(version + '\n' + '\n'.join(lines), encoding='utf-8')
print(f'✅ VERSION обновлён: {version}')
