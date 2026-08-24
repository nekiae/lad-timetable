"""Hello-world: CP-SAT на синтетике 3 класса.

Показывает разницу «только HARD» против «HARD + SOFT с целевой функцией» —
то есть ровно то, что станет демо-сценарием «было/стало».

Запуск:  .venv/bin/python hello.py
"""

import sys
from collections import defaultdict

sys.path.insert(0, "src")

from lad.demo_data import build
from lad.solve import solve

SHORT = {"mat": "Матем", "rus": "Рус", "bel": "Бел", "ist": "История",
         "fiz": "Физра", "ino": "Ин.яз"}
DAYS = ["", "Пн", "Вт", "Ср", "Чт", "Пт"]
W = 18


def metrics(school, lessons):
    """Метрики считаются ОДНИМ кодом для любого расписания (CLAUDE.md §8.3)."""
    class_busy: dict[tuple[str, int], set[int]] = defaultdict(set)
    teacher_busy: dict[tuple[str, int], set[int]] = defaultdict(set)
    for lesson in lessons:
        for class_id in school.group(lesson.group_id).class_ids:
            class_busy[class_id, lesson.slot.day].add(lesson.slot.period)
        teacher_busy[lesson.teacher_id, lesson.slot.day].add(lesson.slot.period)

    class_gaps = sum(
        len(set(range(1, max(p) + 1)) - p) for p in class_busy.values()
    )
    teacher_gaps = sum(
        len(set(range(min(p), max(p) + 1)) - p) for p in teacher_busy.values()
    )
    teacher_days = len(teacher_busy)
    spread = 0
    for c in school.classes:
        counts = [len(class_busy[c.id, d]) for d in range(1, 6)]
        spread += max(counts) - min(counts)
    return class_gaps, teacher_gaps, teacher_days, spread


def show(school, lessons):
    for c in school.classes:
        print(f"--- {c.name} " + "-" * (W * 5 - 7))
        grid: dict[tuple[int, int], list[str]] = defaultdict(list)
        for lesson in lessons:
            group = school.group(lesson.group_id)
            if c.id in group.class_ids:
                mark = "" if group.is_whole_class else f"·{group.part}"
                grid[lesson.slot.period, lesson.slot.day].append(SHORT[lesson.subject_id] + mark)
        print("    " + "".join(f"{DAYS[d]:<{W}}" for d in range(1, 6)))
        for period in range(1, school.periods_per_day + 1):
            row = "".join(f"{'/'.join(sorted(grid[period, d])) or '—':<{W}}" for d in range(1, 6))
            print(f"{period}.  {row}")
        print()


school = build()
print(f"Школа: {school.name}")
print(f"  классов: {len(school.classes)}, групп: {len(school.groups)}, "
      f"учителей: {len(school.teachers)}, часов: {sum(i.hours_per_week for i in school.load)}\n")

raw = solve(school, optimize=False)
opt = solve(school, optimize=True)

show(school, opt.lessons)

print("=" * 66)
print(f"{'метрика':<34}{'только HARD':>15}{'HARD+SOFT':>15}")
print("-" * 66)
labels = ["окон у классов (HARD-8)", "окон у учителей (SOFT-1)",
          "выходов учителей в школу (SOFT-3)", "разброс нагрузки по дням (SOFT-5)"]
for label, a, b in zip(labels, metrics(school, raw.lessons), metrics(school, opt.lessons)):
    print(f"{label:<34}{a:>15}{b:>15}")
print("-" * 66)
print(f"{'время солвера, с':<34}{raw.wall_time:>15.2f}{opt.wall_time:>15.2f}")
print(f"{'сумма штрафов':<34}{'—':>15}{opt.penalty:>15}")
print(f"\nстатус: {opt.status}")
