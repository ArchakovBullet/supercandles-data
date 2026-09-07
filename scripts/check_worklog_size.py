"""Проверка размера WORK_LOG.md и уведомление в VK при превышении."""
import os
from pathlib import Path
from datetime import datetime

WORK_LOG_PATH = Path('/root/finlab/WORK_LOG.md')
MAX_SIZE = 200 * 1024  # 200 КБ

# VK
VK_TOKEN = os.getenv('VK_TOKEN', '')
VK_GROUP_ID = os.getenv('VK_GROUP_ID', '497763452')


def send_vk_message(message):
    """Отправить сообщение в VK."""
    if not VK_TOKEN:
        print("❌ VK_TOKEN не настроен")
        return False
    try:
        import requests
        response = requests.post(
            'https://api.vk.com/method/messages.send',
            params={
                'access_token': VK_TOKEN,
                'peer_id': VK_GROUP_ID,
                'message': message,
                'random_id': int(datetime.now().timestamp() * 1000),
                'v': '5.131'
            }
        )
        return response.json().get('response', False)
    except Exception as e:
        print(f"❌ Ошибка отправки VK: {e}")
        return False


def main():
    """Основная функция."""
    if not WORK_LOG_PATH.exists():
        print(f'❌ Файл не найден: {WORK_LOG_PATH}')
        return

    size = WORK_LOG_PATH.stat().st_size
    size_kb = size / 1024
    print(f'📄 WORK_LOG.md: {size_kb:.1f} КБ (макс: {MAX_SIZE/1024:.0f} КБ)')

    if size > MAX_SIZE:
        message = (
            f'⚠️ WORK_LOG.md превысил допустимый размер:\n'
            f'📄 Текущий: {size_kb:.1f} КБ\n'
            f'📊 Максимум: {MAX_SIZE/1024:.0f} КБ\n\n'
            f'Действие: заархивируйте старые записи (перенесите в архивный файл)'
        )
        print(f'⚠️ Превышение размера! Отправка VK...')
        if send_vk_message(message):
            print('✅ VK-уведомление отправлено')
        else:
            print('❌ Ошибка отправки VK')
    else:
        print('✅ Размер в норме')


if __name__ == '__main__':
    main()
