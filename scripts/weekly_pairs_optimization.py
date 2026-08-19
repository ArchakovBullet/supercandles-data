#!/usr/bin/env python3
"""Еженедельная переоптимизация парной торговли."""
import sys
import json
from pathlib import Path
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

# Добавляем пути
sys.path.insert(0, '/root/finlab')
sys.path.insert(0, '/root/finlab/FinLabPy')

import pandas as pd
import numpy as np
import vk_api

# ========== КОНФИГ ==========
TOKEN = "vk1.a.SlI9YR5W8dTnTYhVLlhNxXEmgDo6rImtWM1jEIpsZKb9KR8EB_x325YDm_Piu1QZffsffqKethgXWlBH3G0e_6h9DUmZEVzbCmXajTm3jW33hE1F49dUOVtjHGRLYN_5pYOnLN0ZiFpdu_DVVqPHLfShNWDBN1prFS7Yf1ec-PE75C_hhs5Mo7SANbnE_uWzA3dGP3_l3So8HfcUVW3f8A"
ADMIN_ID = 497763452

CANDLES_DIR = Path('/root/finlab/data/candles')
CONFIG_FILE = Path('/root/finlab/FinLabPy/My_Indicators/pairs_config.json')

# Пары для оптимизации (лучшие с прошлой сессии)
PAIRS = [
    # Нефтяной сектор
    ('LKOH', 'HYDR'),
    ('LKOH', 'ROSN'),
    ('LKOH', 'TATN'),
    ('ROSN', 'TATN'),
    ('LKOH', 'IRAO'),
    # Энергетика
    ('HYDR', 'IRAO'),
]

# Таймфреймы
TIMEFRAMES = ['M10', 'H1', 'H4', 'D1']


def send_vk_message(vk, peer_id, message):
    """Отправить сообщение в VK."""
    try:
        vk.messages.send(
            peer_id=peer_id,
            message=message,
            random_id=int(datetime.now().timestamp() * 1000)
        )
        return True
    except Exception as e:
        print(f"❌ Ошибка отправки VK: {e}")
        return False


def optimize_all_pairs():
    """Оптимизировать все пары на всех таймфреймах."""
    from My_Indicators.pairs_optimizer import optimize_pair, save_pair_config
    
    results = []
    errors = []
    
    for tf in TIMEFRAMES:
        print(f"\n{'='*60}")
        print(f"📊 Оптимизация на {tf}")
        print(f"{'='*60}")
        
        for pair_a, pair_b in PAIRS:
            pair_name = f"{pair_a}-{pair_b}_{tf}"
            print(f"\n  📊 {pair_name}")
            
            file_a = CANDLES_DIR / f"{pair_a}_{tf}.parquet"
            file_b = CANDLES_DIR / f"{pair_b}_{tf}.parquet"
            
            if not file_a.exists() or not file_b.exists():
                print(f"    ❌ Нет данных")
                errors.append(f"{pair_name}: нет данных")
                continue
            
            try:
                df_a = pd.read_parquet(file_a)
                df_b = pd.read_parquet(file_b)
                
                result = optimize_pair(df_a, df_b, pair_name)
                
                if result:
                    save_pair_config(result)
                    results.append({
                        'pair': pair_name,
                        'sharpe': result.get('train_score', 0),
                        'adf_pvalue': result.get('adf', {}).get('p_value', 1.0),
                        'test_trades': result.get('test_metrics', {}).get('num_trades', 0),
                        'test_winrate': result.get('test_metrics', {}).get('win_rate', 0),
                        'test_pnl': result.get('test_metrics', {}).get('total_pnl', 0)
                    })
                    print(f"    ✅ Sharpe={result['train_score']}, "
                          f"ADF={result['adf']['p_value']}, "
                          f"Trades={result['test_metrics'].get('num_trades', 0)}")
                else:
                    print(f"    ❌ Недостаточно данных")
                    errors.append(f"{pair_name}: недостаточно данных")
            
            except Exception as e:
                print(f"    ❌ Ошибка: {e}")
                errors.append(f"{pair_name}: {e}")
    
    return results, errors


def main():
    """Основная функция."""
    print("=" * 60)
    print("ЕЖЕНЕДЕЛЬНАЯ ПЕРЕОПТИМИЗАЦИЯ ПАРНОЙ ТОРГОВЛИ")
    print(f"Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # Инициализация VK
    vk_session = vk_api.VkApi(token=TOKEN)
    vk = vk_session.get_api()
    
    # Оптимизация
    results, errors = optimize_all_pairs()
    
    # Формируем сообщение
    message_lines = []
    message_lines.append("📊 Еженедельная переоптимизация парной торговли")
    message_lines.append(f"Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    message_lines.append("")
    
    if results:
        message_lines.append(f"✅ Оптимизировано пар: {len(results)}")
        
        # Лучшие пары (по Sharpe)
        sorted_results = sorted(results, key=lambda x: x['sharpe'], reverse=True)
        
        message_lines.append("\n🏆 Топ-5 пар:")
        for i, r in enumerate(sorted_results[:5], 1):
            message_lines.append(f"{i}. {r['pair']}: Sharpe={r['sharpe']}, "
                               f"ADF={r['adf_pvalue']}, "
                               f"WR={r['test_winrate']*100:.1f}%")
        
        # Стационарные пары
        stationary = [r for r in results if r['adf_pvalue'] < 0.05]
        if stationary:
            message_lines.append(f"\n✅ Стационарные пары: {len(stationary)}")
            for r in stationary:
                message_lines.append(f"  - {r['pair']} (ADF={r['adf_pvalue']})")
    
    if errors:
        message_lines.append(f"\n⚠️ Ошибки: {len(errors)}")
        for e in errors[:5]:
            message_lines.append(f"  - {e}")
    
    message = "\n".join(message_lines)
    
    # Отправить в VK
    print("\n" + message)
    if send_vk_message(vk, ADMIN_ID, message):
        print("\n✅ VK-уведомление отправлено")
    else:
        print("\n❌ Ошибка отправки VK")
    
    print("\n✅ Переоптимизация завершена")


if __name__ == '__main__':
    main()
