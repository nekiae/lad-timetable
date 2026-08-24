"""Чтение и запись данных: школа и расписание в JSON.

`schedule.json` — граница между солвером и показом (CLAUDE.md §7.1).
Солвер не знает, как расписание рисуют; рендер не знает, откуда оно взялось.
Благодаря этому реальное расписание школы и наше проходят через один и тот же
валидатор и один и тот же рендер.
"""

import json
from pathlib import Path

from .model import (
    BellSchedule, DayKind, Lesson, LessonKind, Level, LoadItem, Norms, Room, RoomKind,
    School, SchoolClass, Shift, Slot, StudyGroup, Subject, Teacher,
)


# ---------------------------------------------------------------- школа

def school_to_dict(school: School) -> dict:
    return {
        "name": school.name,
        "periods_per_day": school.periods_per_day,
        "day_kinds": {str(d): k.value for d, k in school.day_kinds.items()},
        "classes": [
            {"id": c.id, "parallel": c.parallel, "letter": c.letter, "size": c.size,
             "shift": int(c.shift), "language": c.language, "profile": c.profile}
            for c in school.classes
        ],
        "groups": [
            {"id": g.id, "class_ids": g.class_ids, "part": g.part, "size": g.size}
            for g in school.groups
        ],
        "teachers": [
            {"id": t.id, "name": t.name, "subject_ids": t.subject_ids,
             "unavailable": [[s.day, s.period, int(s.shift)] for s in t.unavailable],
             "method_day": t.method_day, "is_external": t.is_external,
             "home_room_id": t.home_room_id, "class_teacher_of": t.class_teacher_of}
            for t in school.teachers
        ],
        "subjects": [
            {"id": s.id, "name": s.name, "level": s.level.value, "difficulty": s.difficulty,
             "required_room": s.required_room.value, "splits_class": s.splits_class}
            for s in school.subjects
        ],
        "rooms": [
            {"id": r.id, "kind": r.kind.value, "capacity": r.capacity, "building": r.building}
            for r in school.rooms
        ],
        "load": [
            {"group_id": i.group_id, "subject_id": i.subject_id, "teacher_id": i.teacher_id,
             "hours_per_week": i.hours_per_week, "kind": i.kind.value, "room_id": i.room_id}
            for i in school.load
        ],
        "bells": [
            {"name": b.name, "shift": int(b.shift),
             "periods": {str(p): list(v) for p, v in b.periods.items()}}
            for b in school.bells
        ],
        "norms": {
            "max_hours_per_week": {str(k): v for k, v in school.norms.max_hours_per_week.items()},
            "max_lessons_per_day": {str(k): v for k, v in school.norms.max_lessons_per_day.items()},
            "lesson_minutes": school.norms.lesson_minutes,
            "max_tests_per_day": school.norms.max_tests_per_day,
            "double_lessons_allowed": school.norms.double_lessons_allowed,
            "difficulty_scale": {
                name: {str(k): v for k, v in by_parallel.items()}
                for name, by_parallel in school.norms.difficulty_scale.items()
            },
        },
    }


def school_from_dict(data: dict) -> School:
    norms_raw = data.get("norms", {})
    norms = Norms(
        max_hours_per_week={int(k): v for k, v in norms_raw.get("max_hours_per_week", {}).items()},
        max_lessons_per_day={int(k): v for k, v in norms_raw.get("max_lessons_per_day", {}).items()},
        lesson_minutes=norms_raw.get("lesson_minutes"),
        max_tests_per_day=norms_raw.get("max_tests_per_day"),
        double_lessons_allowed=norms_raw.get("double_lessons_allowed"),
        difficulty_scale={
            name: {int(k): v for k, v in by_parallel.items()}
            for name, by_parallel in norms_raw.get("difficulty_scale", {}).items()
        },
    )
    return School(
        name=data.get("name", "Школа"),
        periods_per_day=data.get("periods_per_day", 8),
        day_kinds={int(d): DayKind(k) for d, k in data.get("day_kinds", {}).items()}
        or {d: DayKind.LESSONS for d in range(1, 6)} | {6: DayKind.SIXTH_DAY},
        classes=[
            SchoolClass(id=c["id"], parallel=c["parallel"], letter=c["letter"],
                        size=c.get("size", 0), shift=Shift(c.get("shift", 1)),
                        language=c.get("language", "ru"), profile=c.get("profile"))
            for c in data.get("classes", [])
        ],
        groups=[
            StudyGroup(id=g["id"], class_ids=g["class_ids"], part=g.get("part"),
                       size=g.get("size", 0))
            for g in data.get("groups", [])
        ],
        teachers=[
            Teacher(id=t["id"], name=t["name"], subject_ids=t.get("subject_ids", []),
                    unavailable={Slot(s[0], s[1], Shift(s[2])) for s in t.get("unavailable", [])},
                    method_day=t.get("method_day"), is_external=t.get("is_external", False),
                    home_room_id=t.get("home_room_id"), class_teacher_of=t.get("class_teacher_of"))
            for t in data.get("teachers", [])
        ],
        subjects=[
            Subject(id=s["id"], name=s["name"], level=Level(s.get("level", "base")),
                    difficulty=s.get("difficulty"),
                    required_room=RoomKind(s.get("required_room", "regular")),
                    splits_class=s.get("splits_class", False))
            for s in data.get("subjects", [])
        ],
        rooms=[
            Room(id=r["id"], kind=RoomKind(r.get("kind", "regular")),
                 capacity=r.get("capacity", 0), building=r.get("building", "1"))
            for r in data.get("rooms", [])
        ],
        load=[
            LoadItem(group_id=i["group_id"], subject_id=i["subject_id"],
                     teacher_id=i["teacher_id"], hours_per_week=i["hours_per_week"],
                     kind=LessonKind(i.get("kind", "regular")), room_id=i.get("room_id"))
            for i in data.get("load", [])
        ],
        bells=[
            BellSchedule(name=b["name"], shift=Shift(b.get("shift", 1)),
                         periods={int(p): tuple(v) for p, v in b.get("periods", {}).items()})
            for b in data.get("bells", [])
        ],
        norms=norms,
    )


def load_norms(path: str | Path = "data/sanpin_by.json") -> Norms:
    """Прочитать санитарные нормы из первоисточника.

    Величины, которых в СанПиН нет (продолжительность урока, предельная
    недельная нагрузка), остаются пустыми — и зависящие от них ограничения
    просто не применяются. Ничего не додумываем.
    """
    file = Path(path)
    if not file.exists():
        return Norms()
    data = json.loads(file.read_text(encoding="utf-8"))
    scale_raw = data.get("difficulty_scale", {})
    scale = {
        name: {int(k): v for k, v in by_parallel.items()}
        for name, by_parallel in scale_raw.items()
        if not name.startswith("_") and isinstance(by_parallel, dict)
    }
    peak = data.get("peak_days_rule") or {}
    pe = data.get("pe_rule") or {}
    hard = data.get("hard_subjects_rule") or {}
    shift = data.get("shift_rule") or {}
    tests = data.get("tests_rule") or {}
    double = data.get("double_lessons") or {}

    return Norms(
        max_hours_per_week={int(k): v for k, v in (data.get("max_hours_per_week") or {}).items()},
        max_hours_per_week_advanced={
            int(k): v for k, v in (data.get("max_hours_per_week_advanced") or {}).items()
        },
        max_lessons_per_day={int(k): v for k, v in (data.get("max_lessons_per_day") or {}).items()},
        lesson_minutes=data.get("lesson_minutes"),
        max_tests_per_day=data.get("max_tests_per_day"),
        double_lessons_allowed=data.get("double_lessons_allowed"),
        difficulty_scale=scale,
        peak_days_1_4=peak.get("peak_days_1_4") or [],
        peak_days_5_11=peak.get("peak_days_5_11") or [],
        pe_subject=pe.get("subject"),
        pe_no_two_days_in_row=bool(pe.get("no_two_days_in_row")),
        pe_max_first_or_last=pe.get("max_first_or_last_per_week"),
        hard_subjects=hard.get("subjects") or [],
        hard_max_first_or_last=hard.get("max_first_or_last_per_week"),
        hard_parallels=hard.get("parallels") or [],
        second_shift_forbidden_parallels=shift.get("second_shift_forbidden_parallels") or [],
        second_shift_forbidden_if_advanced=shift.get("second_shift_forbidden_if_advanced") or [],
        double_advanced_parallels=double.get("advanced_parallels") or [],
        double_always_allowed=double.get("always_allowed_subjects") or [],
        double_min_parallel_for_labour=double.get("min_parallel_for_labour"),
        double_forbidden_subjects=double.get("forbidden_subjects") or [],
        double_must_be_consecutive=bool(double.get("must_be_consecutive", True)),
        tests_forbidden_last_period=bool(tests.get("forbidden_last_period")),
        tests_optimal_periods=tests.get("optimal_periods") or [],
    )


# ---------------------------------------------------------------- расписание

def lessons_to_dict(lessons: list[Lesson]) -> list[dict]:
    return [
        {"day": l.slot.day, "period": l.slot.period, "shift": int(l.slot.shift),
         "group_id": l.group_id, "subject_id": l.subject_id, "teacher_id": l.teacher_id,
         "room_id": l.room_id, "kind": l.kind.value}
        for l in lessons
    ]


def lessons_from_dict(data: list[dict]) -> list[Lesson]:
    return [
        Lesson(slot=Slot(d["day"], d["period"], Shift(d.get("shift", 1))),
               group_id=d["group_id"], subject_id=d["subject_id"], teacher_id=d["teacher_id"],
               room_id=d.get("room_id"), kind=LessonKind(d.get("kind", "regular")))
        for d in data
    ]


def save_schedule(path: str | Path, school: School, lessons: list[Lesson], meta: dict | None = None):
    """Записать schedule.json — то, что читает рендер."""
    payload = {
        "school": school_to_dict(school),
        "lessons": lessons_to_dict(lessons),
        "meta": meta or {},
    }
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_schedule(path: str | Path) -> tuple[School, list[Lesson], dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return (
        school_from_dict(data["school"]),
        lessons_from_dict(data["lessons"]),
        data.get("meta", {}),
    )
