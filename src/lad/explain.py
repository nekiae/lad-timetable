"""Объяснимость ручной правки: куда можно поставить урок и почему нельзя иначе.

Завуч перетаскивает урок. Пока тянет, сетка подсвечена: зелёная клетка —
можно, жёлтая — можно, но хуже, красная — нельзя. Отпустил в красную —
система говорит, что именно помешает, человеческими словами и со ссылкой
на пункт нормы. Это оружие завуча в разговоре с учителем: «не я не хочу,
а вот п. 94».

Устроено просто и честно: ход применяется к копии сетки, и обе сетки
прогоняются через один и тот же `validate.check`. Разница отчётов и есть
последствия хода. Сверху — проверки, которых в отчёте по готовой сетке
нет, потому что это свойства ВВОДА, а не расписания: недоступные слоты
учителя, методический день, синхронность подгрупп.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field, replace

from .model import Lesson, Level, School, Slot
from .validate import Report, check

DAY_NAMES = {1: "понедельник", 2: "вторник", 3: "среда", 4: "четверг", 5: "пятница",
             6: "суббота"}


@dataclass
class Reason:
    text: str
    source: str | None = None  # пункт нормы, если это норма


@dataclass
class Verdict:
    """Оценка одного хода."""

    level: str  # "ok" — можно, "worse" — можно, но хуже, "no" — нельзя
    blocking: list[Reason] = field(default_factory=list)  # почему нельзя
    costs: list[Reason] = field(default_factory=list)  # чем хуже
    gains: list[Reason] = field(default_factory=list)  # чем лучше
    moved: list[int] = field(default_factory=list)  # какие уроки двигаются вместе
    swapped: list[int] = field(default_factory=list)  # какие уроки встают на их место


def _occupants(school: School, lessons: list[Lesson], moved: list[int], target: Slot) -> list[int]:
    """Уроки тех же классов, что уже стоят в целевой клетке.

    ХОД — ЭТО ОБМЕН, А НЕ ПЕРЕНОС. Проверено 14.09.2026 на школе завуча:
    при простом переносе 39 клеток из 40 оказывались «нельзя». Класс учится
    без окон, сетка у него плотная: вынутый урок оставляет дыру там, откуда
    ушёл, и ложится на чужой урок там, куда пришёл. Завуч так и не работает —
    он меняет два урока местами. Поэтому урок из целевой клетки едет
    на освободившееся место.
    """
    classes = {c for i in moved for c in school.group(lessons[i].group_id).class_ids}
    return [i for i, other in enumerate(lessons)
            if i not in moved and other.slot == target
            and classes & set(school.group(other.group_id).class_ids)]


def apply_move(lessons: list[Lesson], verdict: "Verdict", source: Slot, target: Slot) -> list[Lesson]:
    """Сетка после хода: перенесённые — в цель, вытесненные — на их место."""
    result = list(lessons)
    for i in verdict.moved:
        result[i] = replace(lessons[i], slot=target, room_id=None)
    for i in verdict.swapped:
        result[i] = replace(lessons[i], slot=source, room_id=None)
    return result


def _partners(school: School, lessons: list[Lesson], index: int) -> list[int]:
    """Уроки, которые обязаны переехать вместе с этим.

    Подгруппы одного деления идут в один час (HARD-9): тронул английский
    у первой группы — вторая едет следом, иначе полкласса ждёт в коридоре.
    """
    lesson = lessons[index]
    group = school.group(lesson.group_id)
    if group.part is None:
        return [index]
    together = [index]
    for i, other in enumerate(lessons):
        if i == index or other.slot != lesson.slot or other.subject_id != lesson.subject_id:
            continue
        other_group = school.group(other.group_id)
        if other_group.part is not None and other_group.class_ids == group.class_ids:
            together.append(i)
    return together


def _violation_counter(report: Report) -> Counter:
    return Counter((v.rule, v.what, v.where) for v in report.violations)


def evaluate_move(school: School, lessons: list[Lesson], index: int, target: Slot,
                  before: Report | None = None) -> Verdict:
    """Что будет, если урок `index` (с напарниками по делению) поставить в `target`."""
    moved = _partners(school, lessons, index)
    lesson = lessons[index]
    verdict = Verdict(level="ok", moved=moved,
                      swapped=_occupants(school, lessons, moved, target))
    if lesson.slot == target:
        verdict.swapped = []
        return verdict

    teachers = {t.id: t for t in school.teachers}
    subjects = {s.id: s.name for s in school.subjects}

    # --- свойства ввода: в отчёте по сетке их не видно.
    # Проверяем обе стороны обмена: и тех, кто едет в цель, и тех, кто
    # едет на освободившееся место.
    trips = [(i, target) for i in moved] + [(i, lesson.slot) for i in verdict.swapped]
    for i, slot in trips:
        teacher = teachers.get(lessons[i].teacher_id)
        if teacher is None:
            continue
        if slot.day == teacher.method_day:
            verdict.blocking.append(Reason(
                f"У {teacher.name} {DAY_NAMES.get(slot.day, slot.day)} — методический день"))
        elif slot in teacher.unavailable:
            verdict.blocking.append(Reason(f"{teacher.name} в это время не может работать"))
        elif slot in teacher.disliked:
            verdict.costs.append(Reason(f"{teacher.name} просил(а) не ставить на это время"))

    # --- последствия для сетки: один и тот же валидатор до и после
    after_lessons = apply_move(lessons, verdict, lesson.slot, target)
    before = before or check(school, lessons)
    after = check(school, after_lessons)

    new = _violation_counter(after) - _violation_counter(before)
    gone = _violation_counter(before) - _violation_counter(after)
    for (rule, what, where), _ in new.items():
        source = rule if rule.startswith("п.") else None
        verdict.blocking.append(Reason(_human(what, where), source))
    for (rule, what, where), _ in gone.items():
        verdict.gains.append(Reason("Уходит нарушение: " + _human(what, where),
                                    rule if rule.startswith("п.") else None))

    # Один предмет дважды в день у группы. Солвер ставит так только сдвоенный
    # урок, и только там, где его разрешает п. 65 ССЭТ (повышенный уровень
    # в VIII–XI, трудовое обучение). Ручная правка обязана следовать тем же
    # правилам, иначе завуч руками соберёт то, что система сама бы запретила:
    # найдено 14.09.2026 — вторая физкультура в тот же день предлагалась
    # как «можно, но хуже», хотя физкультуру сдваивать нельзя вовсе.
    same_day = sum(1 for other in after_lessons
                   if other.group_id == lesson.group_id and other.subject_id == lesson.subject_id
                   and other.slot.day == target.day)
    if same_day > 1 and lesson.slot.day != target.day:
        name = subjects.get(lesson.subject_id, "")
        group = school.group(lesson.group_id)
        parallel = max((c.parallel for c in school.classes if c.id in group.class_ids), default=0)
        advanced = any(item.level != Level.BASE for item in school.load
                       if item.group_id == lesson.group_id and item.subject_id == lesson.subject_id)
        if school.norms.double_allowed(name, parallel, advanced):
            verdict.costs.append(Reason(f"«{name}» в этот день уже есть — выйдет сдвоенный урок"))
        else:
            verdict.blocking.append(Reason(
                f"«{name}» в этот день у класса уже есть, а сдваивать этот предмет нельзя",
                "п. 65 ССЭТ"))

    delta_gaps = after.teacher_gaps - before.teacher_gaps
    if delta_gaps > 0:
        verdict.costs.append(Reason(f"Окон у учителей станет больше на {delta_gaps}"))
    elif delta_gaps < 0:
        verdict.gains.append(Reason(f"Окон у учителей станет меньше на {-delta_gaps}"))
    delta_days = after.teacher_days - before.teacher_days
    if delta_days > 0:
        verdict.costs.append(Reason("Учителю придётся приехать в школу в лишний день"))
    elif delta_days < 0:
        verdict.gains.append(Reason("У учителя освободится целый день"))

    # Первой — причина с пунктом нормы: её завуч и назовёт учителю. Совпадение
    # учителей в одном часе — тоже «нельзя», но ссылки на документ у него нет,
    # и в прогоне показа 15.09.2026 оно стояло первым, заслоняя п. 94 ССЭТ.
    verdict.blocking.sort(key=lambda reason: reason.source is None)
    if verdict.blocking:
        verdict.level = "no"
    elif verdict.costs:
        verdict.level = "worse"
    return verdict


def heatmap(school: School, lessons: list[Lesson], index: int) -> dict[str, Verdict]:
    """Оценка всех клеток недели для одного урока — подсветка при перетаскивании.

    Ключ — "день-урок". Отчёт «до» считается один раз на все клетки.
    """
    before = check(school, lessons)
    shift = lessons[index].slot.shift
    return {
        f"{slot.day}-{slot.period}": evaluate_move(school, lessons, index, slot, before)
        for slot in school.lesson_slots(shift)
    }


def _human(what: str, where: str) -> str:
    """«д2/у3» и «день 2» из валидатора → «вторник, 3-й урок»."""
    if where.startswith("д") and "/у" in where:
        day, period = where[1:].split("/у")[:2]
        where = f"{DAY_NAMES.get(int(day), day)}, {period.split('/')[0]}-й урок"
    elif where.startswith("день "):
        where = DAY_NAMES.get(int(where.split()[1]), where)
    elif where.startswith("дни "):
        a, _, b = where[4:].partition(" и ")
        where = f"{DAY_NAMES.get(int(a), a)} и {DAY_NAMES.get(int(b), b)}"
    return what[:1].upper() + what[1:] + (f" ({where})" if where and where != "неделя" else "")
