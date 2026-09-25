"""Придирчивый разбор готового расписания: ищем то, чего не ловит валидатор.

Валидатор проверяет нормы и структурные конфликты — «учитель в двух местах»,
«окно у класса», «физкультура два дня подряд». Но расписание бывает формально
чистым и при этом нерабочим: класс кочует по семи кабинетам, учитель бегает
между этажами каждую перемену, полкласса ждёт, пока вторая половина учится.
Такие вещи завуч видит с первого взгляда, а система — нет.

Здесь каждая проверка написана отдельно от солвера и от валидатора: если
ошибка в модели, она не повторится здесь автоматически.

    .venv/bin/python tools/audit_live.py <school_id>
"""

from __future__ import annotations

import collections
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from server import db  # noqa: E402
from lad.tables import build_school, tables_from_dict  # noqa: E402

SHOW = 4  # сколько примеров показывать на каждую находку


def main(school_id: str) -> int:
    found = db.get_school(school_id)
    row = db.get_schedule(sys.argv[2]) if len(sys.argv) > 2 else db.latest_schedule(school_id)
    if not found or not row:
        print("нет школы или расписания")
        return 1
    doc, _ = found
    school, _problems = build_school(tables_from_dict(doc), doc.get("settings") or {},
                                     doc.get("wishes"), doc.get("targeted"))
    lessons = row["lessons"]
    subject = {s.id: s.name for s in school.subjects}
    teacher = {t.id: t.name for t in school.teachers}
    room_kind = {r.id: r.kind.value for r in school.rooms}
    group = {g.id: g for g in school.groups}
    need_room = {s.id: s.required_room.value for s in school.subjects}
    home = {t.id: t.home_room_id for t in school.teachers if t.home_room_id}

    def classes_of(lesson) -> list[str]:
        g = group.get(lesson["group_id"])
        return list(g.class_ids) if g else []

    def part_of(lesson):
        g = group.get(lesson["group_id"])
        return g.part if g else None

    print(f"{school.name}: {len(lessons)} уроков\n")
    notes: list[tuple[str, list[str]]] = []

    def report(title: str, items: list[str]) -> None:
        notes.append((title, items))

    # 1. Класс кочует по кабинетам. Дети таскают вещи, завуч видит это сразу.
    per_class_day = collections.defaultdict(set)
    for l in lessons:
        if l.get("room_id") and room_kind.get(l["room_id"]) == "regular":
            for c in classes_of(l):
                per_class_day[c, l["day"]].add(l["room_id"])
    roam = sorted(((len(v), c, d) for (c, d), v in per_class_day.items() if len(v) > 2),
                  reverse=True)
    report("Класс за день меняет больше двух обычных кабинетов",
           [f"{c}, день {d}: {n} кабинетов" for n, c, d in roam[:SHOW]] +
           ([f"…всего таких дней: {len(roam)}"] if len(roam) > SHOW else []))

    # 2. Учитель бегает: соседние уроки в разных кабинетах, перемена на переход.
    by_teacher_day = collections.defaultdict(list)
    for l in lessons:
        by_teacher_day[l["teacher_id"], l["day"]].append(l)
    runs = []
    for (tid, day), items in by_teacher_day.items():
        items.sort(key=lambda l: l["period"])
        for a, b in zip(items, items[1:]):
            if b["period"] == a["period"] + 1 and a.get("room_id") and b.get("room_id") \
                    and a["room_id"] != b["room_id"]:
                runs.append(f"{teacher.get(tid, tid)}, день {day}: "
                            f"{a['period']}-й в {a['room_id']} → {b['period']}-й в {b['room_id']}")
    report("Учитель меняет кабинет на перемене", runs[:SHOW] +
           ([f"…всего переходов: {len(runs)}"] if len(runs) > SHOW else []))

    # 3. Предмету нужен спецкабинет, а урок стоит в обычном.
    wrong = []
    for l in lessons:
        want = need_room.get(l["subject_id"], "regular")
        got = room_kind.get(l.get("room_id") or "", None)
        if want != "regular" and got != want:
            wrong.append(f"{subject.get(l['subject_id'])} у {','.join(classes_of(l))}: "
                         f"нужен «{want}», стоит в «{got}»")
    report("Урок не в своём кабинете", wrong[:SHOW] +
           ([f"…всего: {len(wrong)}"] if len(wrong) > SHOW else []))

    # 4. Урок без кабинета вовсе.
    homeless = [f"{subject.get(l['subject_id'])} у {','.join(classes_of(l))}, "
                f"день {l['day']}, урок {l['period']}"
                for l in lessons if not l.get("room_id")]
    report("Урок без кабинета", homeless[:SHOW] +
           ([f"…всего: {len(homeless)}"] if len(homeless) > SHOW else []))

    # 5. Подгруппы одного деления стоят в разное время: полкласса ждёт.
    split_slots = collections.defaultdict(set)
    for l in lessons:
        part = part_of(l)
        if part is not None:
            for c in classes_of(l):
                split_slots[c, l["subject_id"], part].add((l["day"], l["period"]))
    by_split = collections.defaultdict(dict)
    for (c, sid, part), slots in split_slots.items():
        by_split[c, sid][part] = slots
    apart = []
    for (c, sid), parts in by_split.items():
        if len(parts) < 2:
            continue
        big = max(parts.values(), key=len)
        for part, slots in parts.items():
            outside = slots - big
            if outside and slots is not big:
                apart.append(f"{c}, {subject.get(sid)}, группа «{part}»: "
                             f"{len(outside)} ч вне часов большей группы")
    report("Подгруппы одного предмета идут в разное время", apart[:SHOW])

    # 6. Учитель в школе от первой смены до второй: пришёл к восьми, ушёл вечером.
    spans = []
    for (tid, day), items in by_teacher_day.items():
        lo, hi = min(l["period"] for l in items), max(l["period"] for l in items)
        if hi - lo >= 8:
            spans.append((hi - lo, f"{teacher.get(tid, tid)}, день {day}: "
                                   f"с {lo}-го по {hi}-й урок ради {len(items)} уроков"))
    spans.sort(reverse=True)
    report("Учитель в школе почти весь день", [t for _, t in spans[:SHOW]] +
           ([f"…всего таких дней: {len(spans)}"] if len(spans) > SHOW else []))

    # 7. Учитель приехал ради одного урока.
    single = [f"{teacher.get(tid, tid)}, день {day}: {items[0]['period']}-й урок"
              for (tid, day), items in by_teacher_day.items() if len(items) == 1]
    report("Выход в школу ради одного урока", single[:SHOW] +
           ([f"…всего: {len(single)}"] if len(single) > SHOW else []))

    # 8. Один предмет дважды в день не подряд: два урока физики через полдня.
    twice = []
    per_class_subject = collections.defaultdict(list)
    for l in lessons:
        for c in classes_of(l):
            per_class_subject[c, l["day"], l["subject_id"]].append(l["period"])
    for (c, day, sid), periods in per_class_subject.items():
        uniq = sorted(set(periods))
        if len(uniq) > 1 and any(b - a > 1 for a, b in zip(uniq, uniq[1:])):
            twice.append(f"{c}, день {day}, {subject.get(sid)}: уроки {uniq}")
    report("Один предмет дважды в день врозь", twice[:SHOW] +
           ([f"…всего: {len(twice)}"] if len(twice) > SHOW else []))

    # 9. Класс начинает день не с первого урока своей смены.
    late = []
    per_class = collections.defaultdict(list)
    for l in lessons:
        for c in classes_of(l):
            per_class[c, l["day"]].append(l["period"])
    for (c, day), periods in per_class.items():
        start = school.class_window(c)[0]
        if min(periods) != start:
            late.append(f"{c}, день {day}: начинает с {min(periods)}-го, а смена с {start}-го")
    report("Класс начинает день позже начала смены", late[:SHOW] +
           ([f"…всего: {len(late)}"] if len(late) > SHOW else []))

    # 10. Кабинет занят больше, чем вмещает.
    seats = {r.id: max(1, r.parallel_classes) for r in school.rooms}
    busy = collections.Counter()
    for l in lessons:
        if l.get("room_id"):
            busy[l["room_id"], l["day"], l["period"]] += 1
    over = [f"кабинет {rid}, день {d}, урок {p}: {n} уроков при вместимости {seats.get(rid, 1)}"
            for (rid, d, p), n in busy.items() if n > seats.get(rid, 1)]
    report("Кабинет перегружен", over[:SHOW] + ([f"…всего: {len(over)}"] if len(over) > SHOW else []))

    # 11. Учитель сидит не в своём кабинете, хотя он у него есть.
    away = collections.Counter()
    for l in lessons:
        own = home.get(l["teacher_id"])
        if own and l.get("room_id") and l["room_id"] != own:
            away[teacher.get(l["teacher_id"])] += 1
    report("Учитель ведёт не в своём кабинете",
           [f"{name}: {n} уроков" for name, n in away.most_common(SHOW)])

    printed = 0
    for title, items in notes:
        if not items:
            continue
        printed += 1
        print(f"• {title}")
        for line in items:
            print(f"    {line}")
    if not printed:
        print("Придраться не к чему.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "3e8bc4817797"))
