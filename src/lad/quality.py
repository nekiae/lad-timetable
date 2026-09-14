"""Логика расписания сверх норм: то, что завуч заметит первым делом.

Валидатор (`validate.check`) отвечает на вопрос «законно ли». Законное расписание
при этом бывает нелепым: у класса день из 8 уроков рядом с днём из 5, литература
в понедельник и сразу во вторник, учитель едет в школу ради одного урока.
Норм на это нет, но это и есть «логично ли расписание». Разобрано 14.09.2026
на сетке нового солвера (0 нарушений норм):
    • у 17 классов из 24 самый длинный день длиннее самого короткого на 3 урока;
    • у 6 классов пик трудности — понедельник (п. 94 ССЭТ хочет Вт/Ср/Пт);
    • 50 двухчасовых предметов стоят в соседние дни, 11 трёхчасовых — три дня подряд;
    • 27 выходов учителя в школу ради одного урока.

Здесь только ИЗМЕРЕНИЕ, одним кодом для любого варианта алгоритма
(bench/solver.py) — чтобы улучшения сравнивались цифрами.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from .model import Lesson, School


def measure(school: School, lessons: list[Lesson]) -> dict:
    groups = {g.id: g for g in school.groups}
    subjects = {s.id: s.name for s in school.subjects}
    parallel = {c.id: c.parallel for c in school.classes}
    days = sorted(d for d, kind in school.day_kinds.items() if kind.value == "lessons")

    class_slots: dict[str, set] = defaultdict(set)
    # Предмет у класса по дням. Подгруппы одного деления идут синхронно,
    # поэтому считаем урок целого класса или первой подгруппы — без двойного счёта.
    subject_days: dict[tuple[str, str], list[int]] = defaultdict(list)
    difficulty: dict[str, Counter] = defaultdict(Counter)
    for lesson in lessons:
        group = groups[lesson.group_id]
        name = subjects.get(lesson.subject_id, "")
        for class_id in group.class_ids:
            class_slots[class_id].add((lesson.slot.day, lesson.slot.period))
            if group.part in (None, "1"):
                subject_days[class_id, name].append(lesson.slot.day)
                difficulty[class_id][lesson.slot.day] += school.norms.difficulty(name, parallel[class_id]) or 0

    # 1. Ровность дней у класса: самый длинный минус самый короткий.
    spreads = {}
    for class_id, taken in class_slots.items():
        per_day = [sum(1 for d, _ in taken if d == day) for day in days]
        spreads[class_id] = max(per_day) - min(per_day)

    # 2. Понедельник не легче пиковых дней (п. 94: пик — Вт/Ср/Пт).
    monday_heavy = []
    for class_id, by_day in difficulty.items():
        peak = [d for d in school.norms.peak_days(parallel[class_id] or 5) if d in days]
        if 1 in days and peak and by_day[1] >= max(by_day[d] for d in peak):
            monday_heavy.append(class_id)

    # 3–4. Разнесённость предмета по неделе: 2 часа — не в соседние дни,
    # 3 часа — не три дня подряд (к завтрашнему уроку не подготовить домашнее).
    adjacent_two, three_in_row = [], []
    for (class_id, name), on_days in subject_days.items():
        distinct = sorted(set(on_days))
        if len(on_days) == 2 and len(distinct) == 2 and distinct[1] - distinct[0] == 1:
            adjacent_two.append(f"{class_id} {name}")
        if len(on_days) == 3 and len(distinct) == 3 and distinct[2] - distinct[0] == 2:
            three_in_row.append(f"{class_id} {name}")

    # 5. Учителя: день ради одного урока, самый длинный день.
    teacher_days: dict[str, dict[int, int]] = defaultdict(Counter)
    for lesson in lessons:
        teacher_days[lesson.teacher_id][lesson.slot.day] += 1
    single = sum(1 for by_day in teacher_days.values() for n in by_day.values() if n == 1)
    longest = max((n for by_day in teacher_days.values() for n in by_day.values()), default=0)

    return {
        "day_spread_max": max(spreads.values(), default=0),
        "classes_spread_3plus": sum(1 for v in spreads.values() if v >= 3),
        "monday_heavy": len(monday_heavy),
        "adjacent_two": len(adjacent_two),
        "three_in_row": len(three_in_row),
        "teacher_single_days": single,
        "teacher_longest_day": longest,
        "examples": {
            "monday_heavy": monday_heavy[:5],
            "adjacent_two": adjacent_two[:5],
            "three_in_row": three_in_row[:5],
        },
    }
