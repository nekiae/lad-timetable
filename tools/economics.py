"""Юнит-экономика и точка безубыточности ЛАД.

    .venv/bin/python tools/economics.py

Все внешние цифры — с источниками и датой проверки (см. ASSUMPTIONS). Меняешь
допущение здесь — пересчитывается вся таблица; спорить с инвестором про цифру,
которая живёт в голове, нельзя, поэтому она живёт в коде.

Считаем для резидента ПВТ: налог на прибыль 0%, взносы в ФСЗН 34% нанимателя,
но база ограничена однократной средней зарплатой по стране — это и есть главная
льгота парка, и на высоких окладах она экономит заметно. Плюс 1% выручки в
администрацию ПВТ.
"""
from __future__ import annotations

from dataclasses import dataclass

# --- Внешние данные. Проверено 17.09.2026 -----------------------------------
USD = 3.0228           # курс НБ РБ на 17.09.2026
BASE_UNIT = 45.0       # базовая величина с 01.01.2026, пост. Совмина № 651
AVG_WAGE = 3172.0      # средняя зарплата по РБ, июль 2026, Белстат
FSZN_EMPLOYER = 0.34   # взносы нанимателя
HTP_FEE = 0.01         # отчисление резидента ПВТ от выручки
SCHOOLS_BY = 3000      # учреждений общего среднего образования в РБ

# Порог, ниже которого школе не нужна конкурентная процедура на весь год.
# Это не мелочь: цена выше порога добавляет к сделке месяцы и чужие подписи.
SIMPLE_PROCUREMENT = 50 * BASE_UNIT  # 2250 BYN


@dataclass
class Fixed:
    """Постоянные расходы в месяц, BYN."""
    salaries: list[float]   # оклады gross по каждому сотруднику
    accounting: float = 490  # бухгалтер на аутсорсе, нижняя граница рынка Минска
    legal: float = 300       # юрист по потребности, усреднённо
    infra: float = 300       # сервер под солвер, домены, почта
    misc: float = 200

    def payroll(self) -> float:
        """Расход компании на людей: оклад плюс взносы с урезанной базы."""
        return sum(s + FSZN_EMPLOYER * min(s, AVG_WAGE) for s in self.salaries)

    def monthly(self) -> float:
        return self.payroll() + self.accounting + self.legal + self.infra + self.misc

    def yearly(self) -> float:
        return self.monthly() * 12


@dataclass
class Unit:
    """Юнит одной школы за год, BYN."""
    price: float             # подписка за год
    onboarding_price: float  # разовая услуга подключения
    onboarding_cost: float   # перенос нагрузки завуча, обучение — наши часы
    support_cost: float      # поддержка за год, пик в августе
    infra_cost: float        # серверное время на школу

    def first_year_margin(self) -> float:
        revenue = self.price + self.onboarding_price
        return revenue * (1 - HTP_FEE) - self.onboarding_cost - self.support_cost - self.infra_cost

    def renewal_margin(self) -> float:
        return self.price * (1 - HTP_FEE) - self.support_cost - self.infra_cost


def breakeven(fixed: Fixed, unit: Unit, *, renewal: bool) -> float:
    margin = unit.renewal_margin() if renewal else unit.first_year_margin()
    return fixed.yearly() / margin


TEAMS = {
    # Самый дешёвый честный режим: пилоты бесплатные, денег не берём, значит
    # юрлицо, бухгалтер и юрист не нужны вовсе. Остаётся сервер и домен.
    # ПВТ на этой ступени тоже не нужен: его льготы бьют по ФОТ и прибыли,
    # а у нас нет ни того, ни другой — зато есть 1% с выручки и приём
    # документов по расписанию парка. Вступать имеет смысл под наём.
    "Режим пилота: школы бесплатно, юрлица нет": Fixed(
        salaries=[], accounting=0, legal=0, infra=60, misc=10),
    # Влад один и без оклада, но деньги уже берём — а оплату от бюджетного
    # учреждения мимо юрлица не взять, отсюда бухгалтер и юрист.
    "Влад один, без оклада": Fixed(salaries=[]),
    "Двое: Влад без оклада + разработчик": Fixed(salaries=[4000]),
    "Трое (~5к $/мес ФОТ, как считал Стас)": Fixed(salaries=[5000, 5000, 5000]),
    "Шестеро (~10к $/мес ФОТ)": Fixed(salaries=[5000] * 6),
}

PRICES = {
    "900 BYN/год": 900.0,
    "1500 BYN/год": 1500.0,
    "2200 BYN/год": 2200.0,  # ещё под порогом простой закупки
}


def unit_at(price: float) -> Unit:
    # Подключение: перенос нагрузки и обучение завуча — около 8 наших часов.
    # Час считаем по себестоимости сотрудника, а не по рыночной ставке.
    hour = (4000 + FSZN_EMPLOYER * min(4000, AVG_WAGE)) / 168
    return Unit(
        price=price,
        onboarding_price=600,
        onboarding_cost=8 * hour,
        support_cost=4 * hour,
        infra_cost=10,
    )


def main() -> None:
    print(f"Курс {USD} BYN/$, БВ {BASE_UNIT:.0f} BYN, средняя зарплата {AVG_WAGE:.0f} BYN")
    print(f"Порог простой закупки: {SIMPLE_PROCUREMENT:.0f} BYN/год\n")

    print("ЮНИТ ОДНОЙ ШКОЛЫ")
    for label, price in PRICES.items():
        u = unit_at(price)
        print(f"  {label:<14} первый год {u.first_year_margin():7.0f} BYN   "
              f"продление {u.renewal_margin():7.0f} BYN")

    print("\nПОСТОЯННЫЕ РАСХОДЫ")
    for name, f in TEAMS.items():
        print(f"  {name:<40} {f.yearly():9.0f} BYN/год  (${f.yearly() / USD:7.0f})")

    print("\nТОЧКА БЕЗУБЫТОЧНОСТИ, школ на подписке")
    print(f"  {'команда':<40} " + "  ".join(f"{p:>14}" for p in PRICES))
    for name, f in TEAMS.items():
        cells = []
        for price in PRICES.values():
            n = breakeven(f, unit_at(price), renewal=True)
            cells.append(f"{n:6.0f} ({n / SCHOOLS_BY * 100:4.1f}%)")
        print(f"  {name:<40} " + "  ".join(f"{c:>14}" for c in cells))


if __name__ == "__main__":
    main()
