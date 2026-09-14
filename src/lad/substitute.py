"""Замены: учитель отсутствует — кто проведёт его уроки.

Это ежедневная боль школы, больше стартовой сборки (CLAUDE.md §3.3):
утром завуч узнаёт, что учитель заболел, и до звонка должен закрыть его уроки.
Держать в голове, кто из пятидесяти человек свободен на третьем уроке во вторник
и не придётся ли ему ехать в школу ради одного часа, — ровно та работа, которую
система делает за секунду.

Устроено как подсказка, а не решение за завуча. Для каждого урока — несколько
кандидатов по убыванию пригодности и словами, почему:
  • сначала жёсткий отбор: кандидат свободен в этот час и может работать
    (не в недоступный слот из пожеланий);
  • потом порядок: ведёт этот предмет → знает класс → просто свободен;
    внутри — уже в школе в этот день, урок встык с его расписанием без окна.
Методический день, совместительство и потолок уроков в день не исключают
кандидата, а записываются в «чем хуже»: в экстренный день завуч решит сам.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from .model import Lesson, School, Slot


@dataclass
class Candidate:
    teacher_id: str
    name: str
    score: int
    level: str  # "best" — ведёт этот предмет, "good" — знает класс, "possible" — свободен
    reasons: list[str] = field(default_factory=list)  # чем подходит
    costs: list[str] = field(default_factory=list)  # чем хуже


@dataclass
class Need:
    """Один урок отсутствующего учителя и кого можно поставить."""

    index: int  # номер урока в сетке
    period: int
    group_name: str
    subject: str
    room_id: str | None
    candidates: list[Candidate] = field(default_factory=list)
    note: str | None = None  # что ещё можно сделать с уроком


def plan(school: School, lessons: list[Lesson], teacher_id: str, day: int,
         limit: int = 5) -> list[Need]:
    """Кандидаты на каждый урок учителя `teacher_id` в день недели `day`."""
    subjects = {s.id: s.name for s in school.subjects}
    groups = {g.id: g for g in school.groups}

    teaches_subject: dict[str, set[str]] = defaultdict(set)
    teaches_class: dict[str, dict[str, str]] = defaultdict(dict)  # учитель → класс → предмет
    for item in school.load:
        teaches_subject[item.teacher_id].add(item.subject_id)
        for class_id in groups[item.group_id].class_ids:
            teaches_class[item.teacher_id].setdefault(class_id, item.subject_id)
    for teacher in school.teachers:
        teaches_subject[teacher.id].update(teacher.subject_ids)

    periods_of: dict[str, set[int]] = defaultdict(set)  # учитель → уроки в этот день
    class_periods: dict[str, set[int]] = defaultdict(set)  # класс → уроки в этот день
    for lesson in lessons:
        if lesson.slot.day != day:
            continue
        periods_of[lesson.teacher_id].add(lesson.slot.period)
        for class_id in groups[lesson.group_id].class_ids:
            class_periods[class_id].add(lesson.slot.period)

    needs = []
    own = sorted(((i, l) for i, l in enumerate(lessons)
                  if l.teacher_id == teacher_id and l.slot.day == day),
                 key=lambda pair: pair[1].slot.period)
    for index, lesson in own:
        group = groups[lesson.group_id]
        period = lesson.slot.period
        subject = subjects.get(lesson.subject_id, lesson.subject_id)
        label = ", ".join(group.class_ids) + (f" ({group.part} гр.)" if group.part else "")

        candidates = [c for t in school.teachers if t.id != teacher_id
                      if (c := _rate(t, lesson, subject, subjects, group.class_ids,
                                     teaches_subject, teaches_class, periods_of))]
        candidates.sort(key=lambda c: (-c.score, c.name))

        note = None
        if group.part is None and len(group.class_ids) == 1:
            taken = class_periods[group.class_ids[0]]
            if taken and period == max(taken) and period != min(taken):
                note = "Последний урок у класса: если заменить некем, класс можно отпустить раньше."
            elif taken and period == min(taken) and period != max(taken):
                note = "Первый урок у класса: если заменить некем, день можно начать со второго."

        needs.append(Need(index=index, period=period, group_name=label, subject=subject,
                          room_id=lesson.room_id, candidates=candidates[:limit], note=note))
    return needs


def _rate(teacher, lesson: Lesson, subject: str, subjects: dict[str, str], class_ids: list[str],
          teaches_subject, teaches_class, periods_of) -> Candidate | None:
    slot: Slot = lesson.slot
    busy = periods_of[teacher.id]
    if slot.period in busy or slot in teacher.unavailable:
        return None  # занят или не может работать — не кандидат вовсе

    score, reasons, costs = 0, [], []
    level = "possible"
    if lesson.subject_id in teaches_subject[teacher.id]:
        score += 100
        level = "best"
        reasons.append(f"Ведёт «{subject}» — урок пройдёт по программе")
    known = [c for c in class_ids if c in teaches_class[teacher.id]]
    if known:
        score += 30
        if level == "possible":
            level = "good"
        other = subjects.get(teaches_class[teacher.id][known[0]], "")
        reasons.append(f"Знает класс: ведёт у {known[0]} «{other}»")

    if busy:
        score += 20
        if slot.period - 1 in busy or slot.period + 1 in busy:
            score += 15
            reasons.append("В этот день в школе, урок встык с его расписанием")
        elif min(busy) < slot.period < max(busy):
            score += 20
            reasons.append("В этот день в школе, займёт своё окно")
        else:
            score -= 10
            costs.append("В этот день в школе, но между уроками появится окно")
    else:
        score -= 40
        costs.append("В этот день уроков нет — придётся прийти ради замены")

    if teacher.max_per_day and len(busy) + 1 > teacher.max_per_day:
        score -= 30
        costs.append(f"Будет больше его потолка: {teacher.max_per_day} уроков в день")
    if slot in teacher.disliked:
        score -= 15
        costs.append("Просил(а) не ставить на это время")
    if teacher.method_day == slot.day:
        score -= 60
        costs.append("Методический день — придётся вызвать")
    if teacher.is_external:
        score -= 20
        costs.append("Совместитель: в это время может быть в другой школе")

    return Candidate(teacher_id=teacher.id, name=teacher.name, score=score, level=level,
                     reasons=reasons, costs=costs)
