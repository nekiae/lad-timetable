import sys, json
sys.path.insert(0, "src")
from lad.demo_city import build

SCHOOLS = [
    dict(path="data/demo_selo.json", name="Средняя школа д. Дубровка (сельская)",
         per_parallel=1, size=14, periods=7, multi_subject=True, reserve=1.0,
         method_days=3, profiles_on=False),
    dict(path="data/demo_raion.json", name="Средняя школа № 3 (районный центр)",
         per_parallel=2, size=22, periods=8, multi_subject=False, reserve=1.15,
         method_days=6, profiles_on=True),
    dict(path="data/demo_gorod.json", name="Гимназия № 7 (крупная городская)",
         per_parallel=4, size=26, periods=7, multi_subject=False, reserve=1.05,
         method_days=10, profiles_on=True),
]
for cfg in SCHOOLS:
    info = build(**cfg)
    print(f"{cfg['name']}")
    print(f"   классов {info['classes']}, учителей {info['teachers']}, "
          f"кабинетов {info['rooms']}, строк {info['load_rows']}, часов {info['hours']}, "
          f"сетка {cfg['periods']} уроков")
    if info['profiles']: print(f"   профили: {', '.join(info['profiles'][:4])}")
