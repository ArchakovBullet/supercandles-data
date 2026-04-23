import os; import warnings; warnings.filterwarnings('ignore')
from MOEXPy.MOEXPy import MOEXPy
from datetime import datetime, timedelta

token = os.getenv('MOEX_TOKEN')
api = MOEXPy(token=token)

dt_till = datetime.now()
dt_from = dt_till - timedelta(days=3)

data = api.get_futoi('GLDRUBF', dt_from, dt_till)
cols = data['futoi']['columns']
rows = data['futoi']['data']

idx = {c: i for i, c in enumerate(cols)}
print('Колонки:', cols)
print()

print('Первые 5 строк:')
for row in rows[:5]:
    print(f"  date={row[idx['tradedate']]}, clgroup='{row[idx['clgroup']]}', long={row[idx['pos_long']]}, short={row[idx['pos_short']]}")

print()
clgroups = set(row[idx['clgroup']] for row in rows[:500] if row[idx['clgroup']])
print('Уникальные clgroup:', clgroups)
