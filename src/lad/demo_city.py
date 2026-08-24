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
    hours: dict[str, int] = {}
    for _, row in load.iterrows():
        # кабинет, заданный прямо в строке нагрузки (подгруппы труда), важнее
        direct = str(row.get("кабинет") or "").strip()
        kind = direct if direct in ROOM_KINDS and direct != NONE_CHOICE \
            else kind_of.get(str(row["предмет"]), "обычный")
        hours[kind] = hours.get(kind, 0) + int(row["часов"])

    rows, number = [], 101
    for kind, need in sorted(hours.items()):
        if kind == "спортзал":
            count = max(1, math.ceil(need / (periods * pe_days) * 1.05))
        else:
            count = max(1, math.ceil(need / (periods * days) * reserve))
        for _ in range(count):
            label = str(number) if kind == "обычный" else f"{kind.capitalize()} {number}"
            rows.append({"кабинет": label, "тип": kind, "мест": 30})
            number += 1
    return pd.DataFrame(rows)


def build(path: Path | str = "data/school_big.json", periods: int = 8, days: int = 5) -> dict:
    """Собрать данные школы и записать их в файл рабочего места."""
    counts = {p: CLASSES_PER_PARALLEL for p in range(5, 12)}
    sizes = {p: CLASS_SIZE for p in range(5, 12)}
    classes = generate_classes(counts, sizes)

    subjects = generate_subjects(parallels_of(classes), load_plan())
    load, unknown = generate_load(classes)

    # Профили в старших классах: без них X–XI — это семь одинаковых классов,
    # а в городской школе они и есть главный источник сложности расписания.
    profiles = {k: v for k, v in (load_plan().get("profiles") or {}).items()
                if not k.startswith("_")}
    plan_profiles = list(profiles)
    applied = []
    for n, class_name in enumerate([c for c in classes["класс"] if c.startswith(("10", "11"))]):
        profile = plan_profiles[n % len(plan_profiles)]
        load, _ = apply_profile(load, class_name, profiles[profile])
        applied.append(f"{class_name} — {profile}")

    load, teachers = _assign_teachers(load, subjects)
    rooms = _rooms_for(load, subjects, periods=periods, days=days)

    data = {
        "settings": {
            "name": "Средняя школа № 1 (условная городская)",
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
