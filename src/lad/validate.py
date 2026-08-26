"""Валидатор и метрики — ОДИН код для любого расписания.

Жёсткое правило проекта (CLAUDE.md §8.3): метрики «было» и «стало» считает
один и тот же модуль на одной и той же структуре данных. Никаких «для нашего
считаем так, для школьного иначе» — иначе сравнение враньё, и первый же вопрос
завуча его вскроет.

Этот модуль ничего не знает про солвер. Он принимает список уроков — неважно,
откуда: сгенерирован нами или введён из реального расписания школы.
"""

from collections import defaultdict
from dataclasses import dataclass, field

from .model import Lesson, School


@dataclass
class Violation:
    """Нарушение жёсткого ограничения."""

    rule: str  # "HARD-1", "HARD-3", ...
    what: str  # человеческое описание
    where: str  # где именно


@dataclass
class Report:
    """Результат проверки расписания."""

    class_gaps: int = 0  # окна у классов
    teacher_gaps: int = 0  # окна у учителей
    teacher_days: int = 0  # суммарно выходов учителей в школу за неделю
    class_spread: int = 0  # разброс нагрузки класса по дням, в уроках
    shortest_day: int = 0  # самый короткий учебный день по школе, в уроках
    difficulty_spread: int | None = None  # разброс по баллам трудности (п. 88.2)
    lessons_total: int = 0
    violations: list[Violation] = field(default_factory=list)

    @property
    def violations_count(self) -> int:
        return len(self.violations)

    @property
    def norm_violations(self) -> list[Violation]:
        """Нарушения санитарных норм — отдельно от структурных конфликтов.

        Разница существенная. «Учитель в двух классах одновременно» — это
        расписание, которое физически нельзя провести. «Физкультура два дня
        подряд» — расписание провести можно, но оно нарушает постановление.
        В демо-сценарии (CLAUDE.md §6) сравнивается именно вторая цифра.
        """
        return [v for v in self.violations if v.rule.startswith("п.")]

    @property
    def structural_violations(self) -> list[Violation]:
        return [v for v in self.violations if not v.rule.startswith("п.")]

    def summary(self) -> dict[str, int]:
        return {
            "Окон у учителей": self.teacher_gaps,
            "Окон у классов": self.class_gaps,
            "Выходов учителей в школу": self.teacher_days,
            "Разброс нагрузки по дням": self.class_spread,
            "Самый короткий день": self.shortest_day,
            **({"Разброс по трудности (п. 88.2)": self.difficulty_spread}
               if self.difficulty_spread is not None else {}),
            "Нарушений санитарных норм": len(self.norm_violations),
            "Конфликтов в сетке": len(self.structural_violations),
        }


def check(school: School, lessons: list[Lesson]) -> Report:
    report = Report(lessons_total=len(lessons))

    class_busy: dict[tuple[str, int], set[int]] = defaultdict(set)
    teacher_busy: dict[tuple[str, int], set[int]] = defaultdict(set)

    # --- занятость + поиск конфликтов
    teacher_slots: dict[tuple[str, object], list[Lesson]] = defaultdict(list)
    room_slots: dict[tuple[str, object], list[Lesson]] = defaultdict(list)
    class_slots: dict[tuple[str, object], list[Lesson]] = defaultdict(list)

    for lesson in lessons:
        teacher_slots[lesson.teacher_id, lesson.slot].append(lesson)
        if lesson.room_id:
            room_slots[lesson.room_id, lesson.slot].append(lesson)
        for class_id in school.group(lesson.group_id).class_ids:
            class_slots[class_id, lesson.slot].append(lesson)
            class_busy[class_id, lesson.slot.day].add(lesson.slot.period)
        teacher_busy[lesson.teacher_id, lesson.slot.day].add(lesson.slot.period)

    names = {t.id: t.name for t in school.teachers}

    # HARD-1: учитель в двух местах одновременно
    for (teacher_id, slot), items in teacher_slots.items():
        if len(items) > 1:
            report.violations.append(
                Violation("HARD-1", f"{names.get(teacher_id, teacher_id)} ведёт "
                                    f"{len(items)} урока одновременно", str(slot))
            )

    # HARD-3: в кабинете больше уроков, чем он вмещает.
    # Не «занят дважды»: спортзал держит два класса одновременно, каждый со
    # своим учителем, и это норма школы, а не нарушение (Room.parallel_classes).
    room_seats = {room.id: max(1, room.parallel_classes) for room in school.rooms}
    for (room_id, slot), items in room_slots.items():
        seats = room_seats.get(room_id, 1)
        if len(items) > seats:
            report.violations.append(
                Violation("HARD-3",
                          f"в кабинете {room_id} {len(items)} урока сразу, "
                          f"а помещается {seats}", str(slot))
            )

    # HARD-2: у класса два урока сразу.
    # Деление — законное исключение: две подгруппы одного класса имеют право
    # стоять в одном слоте. Нарушение — когда пересекаются целый класс и подгруппа,
    # либо две группы с одинаковой частью.
    for (class_id, slot), items in class_slots.items():
        if len(items) < 2:
            continue
        groups = [school.group(i.group_id) for i in items]
        parts = [g.part for g in groups]
        if any(p is None for p in parts) or len(set(parts)) != len(parts):
            report.violations.append(
                Violation("HARD-2", f"у класса {class_id} {len(items)} урока одновременно "
                                    "(не деление на подгруппы)", str(slot))
            )

    # --- окна
    for periods in class_busy.values():
        report.class_gaps += len(set(range(1, max(periods) + 1)) - periods)
    for periods in teacher_busy.values():
        report.teacher_gaps += len(set(range(min(periods), max(periods) + 1)) - periods)
    report.teacher_days = len(teacher_busy)

    # HARD-8: окно у класса — это нарушение, а не просто метрика
    for (class_id, day), periods in class_busy.items():
        holes = sorted(set(range(1, max(periods) + 1)) - periods)
        if holes:
            report.violations.append(
                Violation("HARD-8", f"у класса {class_id} окно "
                                    f"(урок{'и' if len(holes) > 1 else ''} {', '.join(map(str, holes))})",
                          f"день {day}")
            )

    # --- разброс нагрузки по дням
    days = [d for d, kind in school.day_kinds.items() if kind.value == "lessons"]
    shortest = None
    for c in school.classes:
        counts = [len(class_busy[c.id, d]) for d in days]
        if counts:
            report.class_spread += max(counts) - min(counts)
        # Самый короткий день по школе. Отдельная цифра, потому что средний
        # разброс её прячет: у одного класса может стоять день на два урока,
        # а сумма разбросов по школе почти не изменится. Дни без уроков
        # не в счёт — класс мог и не учиться (шестой день).
        working = [n for n in counts if n]
        if working:
            shortest = min(working) if shortest is None else min(shortest, min(working))
    report.shortest_day = shortest or 0

    # --- разброс по баллам трудности (п. 88.2 СанПиН РБ).
    # Считается только если шкала загружена — иначе метрики просто нет.
    if school.norms.difficulty_scale:
        subject_names = {s.id: s.name for s in school.subjects}
        by_class_day: dict[tuple[str, int], int] = defaultdict(int)
        for lesson in lessons:
            name = subject_names.get(lesson.subject_id, "")
            for class_id in school.group(lesson.group_id).class_ids:
                parallel = next((c.parallel for c in school.classes if c.id == class_id), None)
                score = school.norms.difficulty(name, parallel) if parallel else None
                if score:
                    by_class_day[class_id, lesson.slot.day] += score
        total = 0
        for c in school.classes:
            scores = [by_class_day[c.id, d] for d in days]
            if any(scores):
                total += max(scores) - min(scores)
        report.difficulty_spread = total

    # --- нормы. Применяются ТОЛЬКО если заполнены из первоисточника.
    # Пустая норма не проверяется — вместо того, чтобы проверяться выдуманной цифрой.
    norms = school.norms
    if norms.max_lessons_per_day:
        for c in school.classes:
            limit = norms.max_lessons_per_day.get(c.parallel)
            if limit is None:
                continue
            for day in days:
                count = len(class_busy[c.id, day])
                if count > limit:
                    report.violations.append(
                        Violation("HARD-7", f"у {c.name} {count} уроков при норме {limit}",
                                  f"день {day}")
                    )
    if norms.max_hours_per_week:
        for c in school.classes:
            limit = norms.hours_limit(c.parallel, c.advanced)
            if limit is None:
                continue
            total = sum(len(class_busy[c.id, d]) for d in days)
            if total > limit:
                report.violations.append(
                    Violation("п. 93 ССЭТ",
                              f"у {c.name} {total} часов в неделю при предельной норме {limit}",
                              "неделя")
                )

    _check_p94(school, lessons, class_busy, days, report)
    return report


def _check_p94(school: School, lessons: list[Lesson], class_busy, days, report: Report) -> None:
    """Пункт 94 ССЭТ № 525: физкультура, трудные предметы, дни работоспособности.

    Считается по факту расставленных уроков — поэтому одинаково применим
    и к нашему расписанию, и к реальному школьному (§8.3).
    """
    norms = school.norms
    if not norms.pe_subject and not norms.hard_subjects:
        return

    subject_names = {s.id: s.name for s in school.subjects}
    parallels = {c.id: c.parallel for c in school.classes}

    # последний урок дня у класса — плавающий, зависит от того, сколько их в дне
    last_period = {(cid, day): max(periods) if periods else 0
                   for (cid, day), periods in class_busy.items()}

    pe_days: dict[str, set[int]] = defaultdict(set)
    pe_edges: dict[str, int] = defaultdict(int)
    hard_edges: dict[tuple[str, str], int] = defaultdict(int)

    for lesson in lessons:
        name = subject_names.get(lesson.subject_id, "")
        day, period = lesson.slot.day, lesson.slot.period
        for class_id in school.group(lesson.group_id).class_ids:
            on_edge = period == 1 or period == last_period.get((class_id, day), 0)
            if norms.is_pe(name):
                pe_days[class_id].add(day)
                if on_edge:
                    pe_edges[class_id] += 1
            elif norms.is_hard_subject(name) and parallels.get(class_id, 0) in norms.hard_parallels:
                if on_edge:
                    hard_edges[class_id, name] += 1

    if norms.pe_no_two_days_in_row:
        for class_id, used in pe_days.items():
            pairs = sorted(d for d in used if d + 1 in used)
            for day in pairs:
                report.violations.append(
                    Violation("п. 94 ССЭТ",
                              f"у {class_id} физкультура два дня подряд",
                              f"дни {day} и {day + 1}")
                )

    if norms.pe_max_first_or_last is not None:
        for class_id, count in pe_edges.items():
            if count > norms.pe_max_first_or_last:
                report.violations.append(
                    Violation("п. 94 ССЭТ",
                              f"у {class_id} физкультура {count} раза первым или последним "
                              f"уроком при норме {norms.pe_max_first_or_last}", "неделя")
                )

    if norms.hard_max_first_or_last is not None:
        for (class_id, name), count in hard_edges.items():
            if count > norms.hard_max_first_or_last:
                report.violations.append(
                    Violation("п. 94 ССЭТ",
                              f"у {class_id} «{name}» {count} раза первым или последним уроком "
                              f"при норме {norms.hard_max_first_or_last}", "неделя")
                )
