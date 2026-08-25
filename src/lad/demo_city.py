"""Условная городская средняя школа — данные для нагрузочной проверки.

ЭТО НЕ ДАННЫЕ РЕАЛЬНОЙ ШКОЛЫ (§8.1 CLAUDE.md: настоящее демо строится
на расписании школы Влада). Здесь проверяется, что система держит масштаб
крупной городской школы: 28 классов V–XI, ~60 учителей, ~900 часов в неделю.

Что взято из первоисточника, а что придумано:
  • часы по предметам — типовой учебный план № 75 (`data/plan_75.json`),
    через тот же `generate_load`, которым пользуется завуч;
  • профили X–XI — оттуда же (`profiles` в plan_75.json);
  • ФИО учителей, номера кабинетов, количество классов в параллели —
    ПРИДУМАНЫ. Это правдоподобная модель, а не отчётность.

Кабинетный фонд не выбирается «на глаз»: он считается из самой нагрузки
(`_rooms_for`). Иначе получается школа, где физкультуры больше, чем часов
в спортзале, и солвер честно отвечает «решения нет» — но по вине данных,
а не модели.

Запуск:  PYTHONPATH=src .venv/bin/python -m lad.demo_city
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

from .tables import (
    DATA_FILE, NONE_CHOICE, ROOM_KINDS, apply_profile, generate_classes,
    generate_load, generate_subjects, load_plan, parallels_of,
)

# Четыре класса в параллели V–XI — типичная городская школа на ~700 учеников.
CLASSES_PER_PARALLEL = 4
CLASS_SIZE = 25

# Ставка учителя, из которой считается, сколько преподавателей нужно предмету.
# 20 часов — округлённая недельная норма, чтобы у каждого оставался запас
# на классное руководство и факультативы.
HOURS_PER_TEACHER = 20

SURNAMES = [
    "Адамович", "Барановский", "Верещако", "Гаврилюк", "Дземідзенка", "Ермакович",
    "Жуковец", "Зайцева", "Иванюк", "Кавалёнак", "Лещенко", "Мельник", "Навумчык",
    "Осипович", "Пашкевич", "Рабцевич", "Савицкая", "Талерчик", "Урбанович",
    "Федорович", "Хмялеўская", "Царук", "Чигирь", "Шчарбак", "Щербович", "Юркевич",
    "Яскевич", "Абрамчук", "Бондарь", "Válchak", "Галушко", "Дорошевич", "Ермолович",
    "Жданович", "Зенькевич", "Ильинчик", "Кузьмич", "Лапицкая", "Матусевич",
    "Нестерович", "Однорог", "Панкевич", "Романчук", "Сакович", "Тарасевич",
    "Ульянович", "Филиппович", "Хвостов", "Цыбулько", "Чернявская", "Шумский",
    "Юхневич", "Ярошевич", "Астапович", "Белькевич", "Ващенко", "Гринкевич",
    "Дубовик", "Емельянчик", "Жилинский", "Зарецкая", "Игнатович", "Кот",
    "Лукашевич", "Мисюкевич", "Новик", "Пилипчук", "Радкевич", "Сурмач",
]
INITIALS = ["А. А.", "В. И.", "Г. С.", "Д. М.", "Е. П.", "И. Н.", "К. В.", "Л. А.",
            "М. С.", "Н. Ф.", "О. В.", "П. Р.", "С. Л.", "Т. А.", "У. М.", "Ф. К."]


def _names(count: int) -> list[str]:
    """Список несовпадающих ФИО. Инициалы перебираются вслед за фамилиями."""
    out = []
    for n in range(count):
        surname = SURNAMES[n % len(SURNAMES)]
        initials = INITIALS[(n // len(SURNAMES) + n) % len(INITIALS)]
        name = f"{surname} {initials}"
        while name in out:
            initials = INITIALS[(INITIALS.index(initials) + 1) % len(INITIALS)]
            name = f"{surname} {initials}"
        out.append(name)
    return out


def _assign_teachers(load: pd.DataFrame, subjects: pd.DataFrame) -> pd.DataFrame:
    """Раздать предметы учителям так, чтобы никто не превысил ставку.

    Учитель ведёт один предмет во всех своих классах — так и устроена школа.
    Классы предмета режутся на примерно равные доли по числу учителей.
    """
    load = load.copy()
    total_names = _names(200)
    used = 0
    teachers_of: dict[str, list[str]] = {}

    for subject in sorted(load["предмет"].unique()):
        rows = load[load["предмет"] == subject]
        hours = int(rows["часов"].sum())
        count = max(1, math.ceil(hours / HOURS_PER_TEACHER))
        # Делимому предмету нужно не меньше учителей, чем подгрупп в классе:
        # подгруппы занимаются ОДНОВРЕМЕННО, и один человек их не проведёт.
        # На малой школе часов мало, счёт по ставке давал одного учителя —
        # и данные выходили заведомо нерешаемыми.
        parts = max((len({str(v).strip() for v in group["подгруппа"] if str(v).strip()})
                     for _, group in rows.groupby("класс")), default=0)
        count = max(count, parts)
        names = total_names[used:used + count]
        used += count
        teachers_of[subject] = names

        # Ключ раздачи — класс вместе с подгруппой: две подгруппы одного класса
        # идут ОДНОВРЕМЕННО, значит вести их обязаны разные учителя.
        keys = sorted({(str(r["класс"]), str(r["подгруппа"])) for _, r in rows.iterrows()})
        for n, key in enumerate(keys):
            who = names[n % count]
            mask = ((load["предмет"] == subject)
                    & (load["класс"] == key[0])
                    & (load["подгруппа"].astype(str) == key[1]))
            load.loc[mask, "учитель"] = who

    teachers = pd.DataFrame({
        "ФИО": [n for names in teachers_of.values() for n in names],
        "методический день": "",
        "свой кабинет": NONE_CHOICE,
    })
    return load, teachers


def _merge_small_loads(load: pd.DataFrame, teachers: pd.DataFrame,
                       target: int = HOURS_PER_TEACHER) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Свести учителей с малой нагрузкой в многопредметников.

    Это не упрощение, а реальность малой школы. При семи классах на всю школу
    география даёт 7 часов в неделю, химия — 6: отдельного учителя на такой
    предмет не берут, их ведёт один человек. Для расписания это принципиально
    другой человек: занятость у него складывается по ВСЕМ его предметам, и в
    два места одновременно он всё так же не встанет. Именно здесь модель
    легче всего сломать, поэтому такую школу и надо проверять отдельно.

    Предметы соединяются по убыванию часов, пока сумма не подойдёт к ставке.
    Это модель, а не отчётность: в жизни сочетания диктует диплом
    (физика с математикой, история с обществоведением), а не арифметика.
    """
    load = load.copy()
    hours = load.groupby("учитель")["часов"].sum().sort_values(ascending=False)
    small = [(name, int(total)) for name, total in hours.items() if total < target * 0.6]

    # Кого с кем соединять НЕЛЬЗЯ: тех, кто ведёт разные подгруппы одного
    # класса по одному предмету. Они работают в один и тот же час, и слить
    # их в одного человека — значит получить заведомо невыполнимые данные.
    # Именно так и вышло на первом прогоне сельской школы: труд у мальчиков
    # и у девочек достался одному Царуку, потому что у обоих было мало часов.
    parallel_pairs: set[frozenset] = set()
    for _, group in load.groupby(["предмет", "класс"]):
        parts = {str(v).strip() for v in group["подгруппа"] if str(v).strip()}
        if len(parts) < 2:
            continue
        who = sorted({str(v) for v in group["учитель"] if str(v).strip()})
        for a in range(len(who)):
            for b in range(a + 1, len(who)):
                parallel_pairs.add(frozenset({who[a], who[b]}))

    def clashes(candidate: str, group: list[str]) -> bool:
        return any(frozenset({candidate, member}) in parallel_pairs for member in group)

    renames: dict[str, str] = {}
    bucket: list[str] = []
    filled = 0
    for name, total in small:
        if bucket and (filled + total > target or clashes(name, bucket)):
            for old_name in bucket[1:]:
                renames[old_name] = bucket[0]
            bucket, filled = [], 0
        bucket.append(name)
        filled += total
    for old_name in bucket[1:]:
        renames[old_name] = bucket[0]

    if renames:
        load["учитель"] = load["учитель"].replace(renames)
        teachers = teachers[~teachers["ФИО"].isin(renames)].reset_index(drop=True)
    return load, teachers


def _rooms_for(load: pd.DataFrame, subjects: pd.DataFrame, periods: int, days: int,
               reserve: float = 1.25) -> pd.DataFrame:
    """Кабинетный фонд под конкретную нагрузку, а не «на глаз».

    Часы, которым нужен спецкабинет, делятся на число слотов в неделе: столько
    кабинетов надо минимально. Запас `reserve` — потому что уроки нельзя
    размазать идеально ровно (у класса свои ограничения по дням).

    Спортзал считается отдельно, и это не мелочь. П. 94 ССЭТ запрещает
    физкультуру два дня подряд: при трёх часах и пятидневке остаются ровно
    понедельник, среда и пятница — у ВСЕХ классов сразу. Значит зал нужен
    не «в среднем по неделе», а по пиковому дню, и делить надо на треть недели.
    Первый прогон на 28 классах это и вскрыл: 28 классов против 24 мест
    в понедельник — INFEASIBLE, причём по вине кабинетного фонда, а не модели.
    """
    pe_days = math.ceil(days / 2)  # понедельник, среда, пятница
    kind_of = {str(r["предмет"]): str(r["кабинет"]) for _, r in subjects.iterrows()}

    def room_kind(row) -> str:
        """Тип кабинета для строки нагрузки.

        Кабинет, заданный прямо в строке (подгруппы труда расходятся в разные
        мастерские), важнее типа, заданного предметом. Пустое значение здесь —
        это NONE_CHOICE «—», а не пустая строка: проверять надо именно его,
        иначе прочерк принимается за осмысленный выбор.
        """
        direct = str(row.get("кабинет") or "").strip()
        if direct in ROOM_KINDS and direct != NONE_CHOICE:
            return direct
        return kind_of.get(str(row["предмет"]), "обычный")

    hours: dict[str, int] = {}
    for _, row in load.iterrows():
        hours[room_kind(row)] = hours.get(room_kind(row), 0) + int(row["часов"])

    # Сколько подгрупп одновременно просится в кабинет каждого типа. Деление
    # на подгруппы идёт СИНХРОННО (HARD-9), поэтому информатика в две подгруппы
    # требует двух компьютерных кабинетов физически — сколько бы часов ни было
    # в неделю. Расчёт «по часам» этого не видит: часов мало, а кабинет нужен
    # второй. В малой школе на 7 классов это и вскрылось.
    parallel_need: dict[str, int] = {}
    for _, group in load.groupby(["предмет", "класс"]):
        parts = {str(v).strip() for v in group.get("подгруппа", []) if str(v).strip()}
        if len(parts) < 2:
            continue
        # Подгруппы, расходящиеся по РАЗНЫМ типам кабинетов (труд: мастерская
        # и кабинет обслуживающего труда), требуют по одному кабинету каждого
        # типа. Подгруппы одного типа (информатика) — по одному на каждую.
        need_here: dict[str, int] = {}
        for _, row in group.iterrows():
            kind = room_kind(row)
            if kind != "обычный":
                need_here[kind] = need_here.get(kind, 0) + 1
        for kind, count in need_here.items():
            parallel_need[kind] = max(parallel_need.get(kind, 0), count)

    rows, number = [], 101
    for kind, need in sorted(hours.items()):
        if kind == "спортзал":
            count = max(1, math.ceil(need / (periods * pe_days) * 1.05))
        else:
            count = max(1, math.ceil(need / (periods * days) * reserve))
        count = max(count, parallel_need.get(kind, 0))
        for _ in range(count):
            label = str(number) if kind == "обычный" else f"{kind.capitalize()} {number}"
            rows.append({"кабинет": label, "тип": kind, "мест": 30})
            number += 1
    return pd.DataFrame(rows)


def build(path: Path | str = "data/school_big.json", periods: int = 8, days: int = 5,
          per_parallel: int = CLASSES_PER_PARALLEL, size: int = CLASS_SIZE,
          name: str = "Средняя школа № 1 (условная городская)",
          multi_subject: bool = False, reserve: float = 1.25,
          method_days: int = 0, profiles_on: bool = True) -> dict:
    """Собрать данные школы и записать их в файл рабочего места.

    Параметры существуют, чтобы проверять систему на РАЗНЫХ школах, а не на
    одной. Размер, теснота сетки, кабинетный фонд и совмещение предметов
    меняют задачу качественно, а не количественно:
      • `per_parallel`  — сколько классов в параллели (село: 1, город: 4);
      • `periods`       — высота сетки; 7 вместо 8 убирает запас и делает
                          расписание по-настоящему тесным;
      • `multi_subject` — учителя-многопредметники (малая школа);
      • `reserve`       — запас кабинетного фонда; 1.0 значит «впритык»;
      • `method_days`   — скольким учителям дать день без уроков.
    """
    counts = {p: per_parallel for p in range(5, 12)}
    sizes = {p: size for p in range(5, 12)}
    classes = generate_classes(counts, sizes)

    subjects = generate_subjects(parallels_of(classes), load_plan())
    load, unknown = generate_load(classes)

    # Профили в старших классах: без них X–XI — это семь одинаковых классов,
    # а в городской школе они и есть главный источник сложности расписания.
    profiles = {k: v for k, v in (load_plan().get("profiles") or {}).items()
                if not k.startswith("_")}
    plan_profiles = list(profiles)
    applied = []
    if profiles_on:
        for n, class_name in enumerate(
                [c for c in classes["класс"] if c.startswith(("10", "11"))]):
            profile = plan_profiles[n % len(plan_profiles)]
            load, _ = apply_profile(load, class_name, profiles[profile])
            applied.append(f"{class_name} — {profile}")

    load, teachers = _assign_teachers(load, subjects)
    if multi_subject:
        load, teachers = _merge_small_loads(load, teachers)
    # Методический день — реальная практика: у учителя есть день без уроков.
    # Для солвера это жёсткий запрет на пять слотов подряд, и на тесной сетке
    # он ощутимо усложняет задачу. Раздаём по кругу, чтобы школа не осталась
    # без целой параллели предметов в один день.
    if method_days:
        for n in range(min(method_days, len(teachers))):
            teachers.loc[n, "методический день"] = str(n % days + 1)
    rooms = _rooms_for(load, subjects, periods=periods, days=days, reserve=reserve)

    data = {
        "settings": {
            "name": name,
            "periods": periods, "days": days, "sixth_day": True, "intro_seen": True,
        },
        "tables": {
            "classes": classes.to_dict("records"),
            "subjects": subjects.to_dict("records"),
            "teachers": teachers.to_dict("records"),
            "rooms": rooms.to_dict("records"),
            "load": load.to_dict("records"),
        },
        "wishes": {},
    }
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "path": str(path),
        "classes": len(classes), "teachers": len(teachers), "subjects": len(subjects),
        "rooms": len(rooms), "load_rows": len(load), "hours": int(load["часов"].sum()),
        "profiles": applied, "unknown_hours": unknown,
    }


if __name__ == "__main__":
    info = build()
    print(json.dumps(info, ensure_ascii=False, indent=2))
