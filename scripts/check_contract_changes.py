#!/usr/bin/env python3
"""Мониторинг изменений контрактов в contract_cache.json с уведомлением в VK."""
import os
import json
import sys
from pathlib import Path
from datetime import datetime

# Добавляем путь для импорта
sys.path.insert(0, '/root/finlab')

import vk_api

# ========== КОНФИГ ==========
TOKEN = os.getenv("VK_TOKEN", "")
GROUP_ID = 238639379
ADMIN_ID = 497763452

CACHE_FILE = Path("/root/finlab/FinLabPy/DataCollectors/contract_cache.json")
STATE_FILE = Path("/root/finlab/logs/contract_state.json")

def load_cache():
    """Загрузить текущий contract_cache.json"""
    with open(CACHE_FILE, 'r') as f:
        return json.load(f)

def load_state():
    """Загрузить предыдущее состояние"""
    if STATE_FILE.exists():
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_state(state):
    """Сохранить текущее состояние"""
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2, default=str)

def check_contract_changes():
    """Проверить изменения контрактов и отправить уведомление"""
    current = load_cache()
    previous = load_state()
    
    if not previous:
        # Первый запуск - просто сохраняем состояние
        save_state(current)
        print("✅ Первый запуск: состояние сохранено")
        return None
    
    changes = []
    for ticker, data in current.items():
        if ticker not in previous:
            changes.append(f"🆕 {ticker}: новый контракт {data.get('code', 'N/A')}")
        elif previous[ticker].get('code') != data.get('code'):
            changes.append(f"🔄 {ticker}: {previous[ticker].get('code', 'N/A')} → {data.get('code', 'N/A')}")
    
    save_state(current)
    
    if changes:
        return "📋 Обновление контрактов:\n" + "\n".join(changes)
    return None

def send_vk_message(vk, peer_id, message):
    """Отправить сообщение в VK"""
    try:
        vk.messages.send(
            peer_id=peer_id,
            message=message,
            random_id=int(datetime.now().timestamp() * 1000)
        )
        return True
    except Exception as e:
        print(f"❌ Ошибка отправки: {e}")
        return False

if __name__ == '__main__':
    # Инициализация VK
    vk_session = vk_api.VkApi(token=TOKEN)
    vk = vk_session.get_api()
    
    # Проверить изменения
    message = check_contract_changes()
    
    if message:
        print(message)
        # Отправить админу
        if send_vk_message(vk, ADMIN_ID, message):
            print("✅ Уведомление отправлено в VK")
    else:
        print("✅ Изменений контрактов не обнаружено")
