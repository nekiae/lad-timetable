"""Сборка School из плоских таблиц ввода.

Отделено от интерфейса намеренно: логика, которую нельзя запустить без Streamlit,
не тестируется. Здесь же живёт арифметическая проверка данных до солвера —
чтобы завуч не получил голое INFEASIBLE (docs/domain.md §4.8).
"""

import json
from pathlib import Path

import pandas as pd

from .model import (
    DayKind, LessonKind, Level, LoadItem, Room, RoomKind, School, SchoolClass, Slot,
    StudyGroup, Subject, Teacher,
)
from .storage import load_norms

DATA_FILE = Path("data/school.json")

ROOM_KINDS = {
    "обычный": RoomKind.REGULAR, "физика": RoomKind.PHYSICS, "химия": RoomKind.CHEMISTRY,
    "биология": RoomKind.BIOLOGY, "компьютерный": RoomKind.COMPUTER, "спортзал": RoomKind.GYM,
    "мастерская (техтруд)": RoomKind.WORKSHOP_TECH,
    "мастерская (обсл. труд)": RoomKind.WORKSHOP_SERVICE,
    "допризывная подготовка": RoomKind.MILITARY, "актовый зал": RoomKind.ASSEMBLY,
}
KIND_BY_VALUE = {v.value: k for k, v in ROOM_KINDS.items()}

# Кабинеты, без которых урок не провести физически: в классной комнате нет
# ни снарядов, ни компьютеров, ни станков. Остальные спецкабинеты (физика,
# химия, биология) желательны, но не обязательны — см. Subject.room_strict.
STRICT_ROOM_KINDS = {
    RoomKind.GYM, RoomKind.COMPUTER,
    RoomKind.WORKSHOP_TECH, RoomKind.WORKSHOP_SERVICE,
}
# Допризывная подготовка и актовый зал сюда НЕ входят: отдельный кабинет
# допризывной подготовки есть далеко не в каждой школе, и урок спокойно идёт
# в обычном классе. Отметить его строгим завуч всегда может галочкой.

# Уровень изучения предмета. В X–XI определяет часы: «4–6» в типовом плане
# значит 4 на базовом уровне и 6 на повышенном.
LEVELS = {"базовый": Level.BASE, "повышенный": Level.ADVANCED, "углублённый": Level.DEEP}

# Тип занятия. Факультативы не входят в предельную недельную нагрузку по-разному
# (п. 93 ССЭТ), но учителя и кабинет занимают — значит в сетке их учитывать надо.
LESSON_KINDS = {
    "урок": LessonKind.REGULAR,
    "факультатив": LessonKind.ELECTIVE,
    "стимулирующее/поддерживающее": LessonKind.SUPPORT,
    "классный час": LessonKind.CLASS_HOUR,
}

DAY_NAMES = {1: "Пн", 2: "Вт", 3: "Ср", 4: "Чт", 5: "Пт", 6: "Сб"}
DAY_NUMBERS = {v: k for k, v in DAY_NAMES.items()}

# Три состояния клетки в сетке пожеланий. Разделение принципиальное:
# «не может» — запрет, «нежелательно» — штраф. Если всё свалить в запреты,
# расписание перестанет существовать (у каждого найдётся своё «только не в пятницу»).
CANT = "✗ не может"
DISLIKE = "~ нежелательно"
# Свободную клетку обозначаем видимым символом, а не пустой строкой: выпадающий
# список Streamlit рисует пустое значение словом «None», и вся сетка выглядела
# заполненной английским мусором.
FREE = "—"
WISH_OPTIONS = [FREE, CANT, DISLIKE]

# То же самое в необязательных выпадающих списках таблиц: «кабинет подгруппы»,
# «свой кабинет учителя». Пустая строка среди вариантов рисуется как «None».
NONE_CHOICE = "—"


def optional(value) -> str:
    """Значение необязательного списка: «—» и пустое считаются «не задано»."""
    text = str(value or "").strip()
    return "" if text in ("", NONE_CHOICE, "None", "nan") else text


def parse_class_name(name: str) -> tuple[int | None, str]:
    """«5А» → (5, «А»), «10Б» → (10, «Б»), «11» → (11, «А»).

    Параллель (год обучения) не спрашивается отдельно: она уже написана
    в названии класса, а лишняя колонка — это лишний способ ошибиться.
    Нужна она для норм: предельная нагрузка и шкала трудности предметов
    зависят от года обучения.
    """
    name = str(name or "").strip()
    digits = ""
    for char in name:
        if char.isdigit():
            digits += char
        else:
            break
    if not digits:
        return None, name or "А"
    return int(digits), name[len(digits):].strip() or "А"


def blank_wishes(days: int = 5, periods: int = 8) -> pd.DataFrame:
    """Пустая сетка день × урок для одного учителя."""
    return pd.DataFrame(
        [[FREE for _ in range(periods)] for _ in range(days)],
        index=[DAY_NAMES[d] for d in range(1, days + 1)],
        columns=[str(p) for p in range(1, periods + 1)],
    )


def wishes_to_grid(saved: dict, days: int = 5, periods: int = 8) -> pd.DataFrame:
    """Из хранимого вида {"hard": [[день, урок]], "soft": [...]} — в сетку."""
    grid = blank_wishes(days, periods)
    for key, mark in (("hard", CANT), ("soft", DISLIKE)):
        for day, period in saved.get(key, []):
            if 1 <= day <= days and 1 <= period <= periods:
                grid.iat[day - 1, period - 1] = mark
    return grid


def grid_to_wishes(grid: pd.DataFrame) -> dict:
    """Обратно: из сетки — в хранимый вид."""
    hard, soft = [], []
    for row, day_name in enumerate(grid.index):
        day = DAY_NUMBERS.get(str(day_name), row + 1)
        for col, period_name in enumerate(grid.columns):
            value = str(grid.iat[row, col] or "")
            target = hard if value.startswith("✗") else (soft if value.startswith("~") else None)
            if target is not None:
                target.append([day, int(period_name)])
    return {"hard": hard, "soft": soft}


# ------------------------------------------------------------------ данные

def blank_tables() -> dict[str, pd.DataFrame]:
    return {
        "classes": pd.DataFrame({"класс": ["5А"], "учеников": [24],
                                 "повышенный уровень": [False]}),
        "subjects": pd.DataFrame({"предмет": ["Математика"], "кабинет": ["обычный"],
                                  "только в нём": [False]}),
        "teachers": pd.DataFrame({"ФИО": ["Иванова И.И."], "методический день": [""],
                                  "свой кабинет": [NONE_CHOICE]}),
        "rooms": pd.DataFrame({"кабинет": ["101"], "тип": ["обычный"], "мест": [30],
                               "классов сразу": [1]}),
        "load": pd.DataFrame({"класс": ["5А"], "предмет": ["Математика"],
                              "учитель": ["Иванова И.И."], "часов": [5], "подгруппа": [""],
                              "уровень": ["базовый"], "тип": ["урок"], "кабинет": [NONE_CHOICE]}),
    }


def load_tables() -> dict[str, pd.DataFrame]:
    """Прочитать таблицы, добив недостающие пустыми бланками.

    Файл может быть неполным: сохранён старой версией, отредактирован руками,
    обнулён. Отсутствие таблицы не должно ронять приложение — вместо неё
    подставляется пустой бланк с нужными колонками.
    """
    tables = blank_tables()
    if not DATA_FILE.exists():
        # Пустые таблицы с правильными колонками. Бланк со строкой-примером
        # («Иванова И.И.») не годится: пример попадёт в данные школы и будет
        # считаться заполненными данными.
        return {name: table.iloc[0:0] for name, table in tables.items()}
    raw = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    tables = {name: table.iloc[0:0] for name, table in tables.items()}
    for name, rows in (raw.get("tables") or {}).items():
        if name in tables:
            table = pd.DataFrame(rows)
            # колонки, добавленные позже (например «повышенный уровень»),
            # в старом файле отсутствуют — дополняем значением по умолчанию
            sample = blank_tables()[name]
            for column in sample.columns:
                if column not in table.columns:
                    table[column] = sample.iloc[0][column] if len(sample) else ""
            tables[name] = table
    # Уже сохранённые файлы держат в необязательных колонках пустую строку —
    # выпадающий список показал бы её как «None». Подменяем на «—».
    for name, column in (("load", "кабинет"), ("teachers", "свой кабинет")):
        table = tables.get(name)
        if table is not None and column in table.columns:
            table[column] = [optional(v) or NONE_CHOICE for v in table[column]]
    return tables


def load_wishes() -> dict:
    """Пожелания учителей: ФИО → {"hard": [[день, урок]], "soft": [...]}."""
    if DATA_FILE.exists():
        raw = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        return raw.get("wishes", {})
    return {}


def save_tables(tables: dict[str, pd.DataFrame], settings: dict, wishes: dict | None = None):
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "tables": {k: v.to_dict("records") for k, v in tables.items()},
        "settings": settings,
        "wishes": wishes if wishes is not None else load_wishes(),
    }
    DATA_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def school_groups_class_ids(groups: dict, group_id: str) -> list[str]:
    group = groups.get(group_id)
    return group.class_ids if group else []


def build_school(tables: dict[str, pd.DataFrame], settings: dict,
                 wishes: dict | None = None) -> tuple[School, list[str]]:
    """Собрать School из таблиц. Возвращает школу и список проблем ввода."""
    problems: list[str] = []
    wishes = wishes or {}

    classes, class_ids, class_rows = [], {}, {}
    for _, row in tables["classes"].iterrows():
        name = str(row["класс"]).strip()
        if not name:
            continue
        parallel, letter = parse_class_name(name)
        if parallel is None:
            problems.append(
                f"класс «{name}»: не могу понять, какой это год обучения. "
                "Название должно начинаться с цифры — «5А», «10Б»"
            )
            continue
        classes.append(SchoolClass(id=name, parallel=parallel, letter=letter,
                                   size=int(row.get("учеников") or 0),
                                   advanced=bool(row.get("повышенный уровень", False))))
        class_rows[name] = row
        class_ids[name] = name

    subjects, subject_ids = [], {}
    for _, row in tables["subjects"].iterrows():
        name = str(row["предмет"]).strip()
        if not name:
            continue
        sid = f"s{len(subjects)}"
        subject_ids[name] = sid
        kind = ROOM_KINDS.get(str(row.get("кабинет")), RoomKind.REGULAR)
        # «Только в нём» отмечают там, где урок без своего кабинета не провести:
        # физкультура, информатика, труд. Физика, химия и биология по умолчанию
        # НЕ строгие — в своём кабинете они идут, когда есть лабораторная,
        # а иначе спокойно занимают обычный класс, и два класса меняются
        # кабинетами по обстоятельствам. Именно так работает живая школа,
        # и без этого один кабинет физики на 24 класса делает расписание
        # невозможным (проверено 26.08.2026).
        strict_default = kind in STRICT_ROOM_KINDS
        raw_strict = row.get("только в нём")
        strict = strict_default if raw_strict is None or str(raw_strict) == "nan" \
            else bool(raw_strict)
        subjects.append(Subject(id=sid, name=name, required_room=kind,
                                room_strict=strict))

    teachers, teacher_ids = [], {}
    for _, row in tables["teachers"].iterrows():
        name = str(row["ФИО"]).strip()
        if not name:
            continue
        tid = f"t{len(teachers)}"
        teacher_ids[name] = tid
        day = str(row.get("методический день") or "").strip()
        wish = wishes.get(name, {})
        teachers.append(Teacher(
            id=tid, name=name,
            method_day=int(day) if day.isdigit() else None,
            home_room_id=optional(row.get("свой кабинет")) or None,
            unavailable={Slot(d, p) for d, p in wish.get("hard", [])},
            disliked={Slot(d, p) for d, p in wish.get("soft", [])},
        ))

    rooms = []
    for _, row in tables["rooms"].iterrows():
        name = str(row["кабинет"]).strip()
        if not name:
            continue
        rooms.append(Room(
            id=name, kind=ROOM_KINDS.get(str(row.get("тип")), RoomKind.REGULAR),
            capacity=int(row.get("мест") or 0),
            # Спортзал держит два класса одновременно — это обычная практика,
            # а не исключение. Пустое значение читаем как единицу.
            parallel_classes=max(1, int(row.get("классов сразу") or 1)),
        ))

    # Группы генерируются из нагрузки: пустая «подгруппа» = весь класс.
    groups: dict[str, StudyGroup] = {}
    load: list[LoadItem] = []
    for n, row in tables["load"].iterrows():
        class_name = str(row["класс"]).strip()
        subject_name = str(row["предмет"]).strip()
        teacher_name = str(row["учитель"]).strip()
        if not (class_name and subject_name and teacher_name):
            continue
        if class_name not in class_ids:
            problems.append(f"строка нагрузки {n + 1}: класс «{class_name}» не заведён")
            continue
        if subject_name not in subject_ids:
            problems.append(f"строка нагрузки {n + 1}: предмет «{subject_name}» не заведён")
            continue
        if teacher_name not in teacher_ids:
            problems.append(f"строка нагрузки {n + 1}: учитель «{teacher_name}» не заведён")
            continue

        part = str(row.get("подгруппа") or "").strip() or None
        gid = class_name if part is None else f"{class_name}·{subject_name}·{part}"
        if gid not in groups:
            groups[gid] = StudyGroup(id=gid, class_ids=[class_name], part=part)
        # «кабинет» в строке нагрузки заполняют только при делении, где подгруппы
        # идут в разные кабинеты (труд). Пусто — берётся тип, заданный предметом.
        room_kind = ROOM_KINDS.get(optional(row.get("кабинет")))
        level = LEVELS.get(str(row.get("уровень") or "").strip(), Level.BASE)
        kind = LESSON_KINDS.get(str(row.get("тип") or "").strip(), LessonKind.REGULAR)
        load.append(LoadItem(group_id=gid, subject_id=subject_ids[subject_name],
                             teacher_id=teacher_ids[teacher_name],
                             hours_per_week=int(row.get("часов") or 0),
                             level=level, kind=kind, room_kind=room_kind))

    # Профильный класс не нужно отмечать галочкой отдельно: если хоть один
    # предмет изучается на повышенном уровне, класс профильный по определению.
    # Это меняет предельную недельную нагрузку (типовой план № 75, сноска 6).
    advanced_classes = {
        cid for item in load if item.level != Level.BASE
        for cid in school_groups_class_ids(groups, item.group_id)
    }
    for c in classes:
        if c.id in advanced_classes:
            c.advanced = True

    periods = int(settings.get("periods", 8))
    lesson_days = int(settings.get("days", 5))
    day_kinds = {d: DayKind.LESSONS for d in range(1, lesson_days + 1)}
    if settings.get("sixth_day", True):
        day_kinds[6] = DayKind.SIXTH_DAY

    school = School(
        name=settings.get("name", "Школа"), classes=classes, groups=list(groups.values()),
        teachers=teachers, subjects=subjects, rooms=rooms, load=load,
        periods_per_day=periods, day_kinds=day_kinds,
        norms=load_norms(),  # санитарные нормы из первоисточника, если файл есть
    )

    # Арифметическая проверка до солвера — чтобы не получить голое INFEASIBLE
    # (docs/domain.md §4.8).
    slots_per_week = len(school.lesson_slots())
    by_teacher: dict[str, int] = {}
    for item in load:
        by_teacher[item.teacher_id] = by_teacher.get(item.teacher_id, 0) + item.hours_per_week
    names = {t.id: t.name for t in teachers}
    for tid, hours in by_teacher.items():
        if hours > slots_per_week:
            problems.append(
                f"у учителя {names[tid]} {hours} часов в неделю, "
                f"а в сетке всего {slots_per_week} уроков — расписание невозможно"
            )
    for c in classes:
        hours = sum(i.hours_per_week for i in load
                    if school.group(i.group_id).class_ids == [c.id]
                    and school.group(i.group_id).part is None)
        if hours > slots_per_week:
            problems.append(f"у класса {c.name} {hours} часов при {slots_per_week} слотах")

    # Подгруппы одного деления идут ОДНОВРЕМЕННО (иначе полкласса ждёт вторую
    # половину). Значит и кабинетов нужно столько же, сколько подгрупп. Один
    # компьютерный класс и деление информатики — это гарантированно нерешаемо,
    # и сказать об этом надо здесь, а не отдавать голое INFEASIBLE.
    # Здесь и ниже важно число ОДНОВРЕМЕННЫХ уроков, а не комнат: спортзал
    # вмещает два класса сразу, и для подгрупп это тоже считается.
    rooms_by_kind: dict = {}
    for room in rooms:
        rooms_by_kind[room.kind] = (rooms_by_kind.get(room.kind, 0)
                                    + max(1, room.parallel_classes))
    subject_room = {s.id: s.required_room for s in subjects}
    subject_name_by_id = {s.id: s.name for s in subjects}
    need: dict[tuple[str, object], int] = {}
    for item in load:
        group = school.group(item.group_id)
        if group.part is None:
            continue
        kind = item.room_kind or subject_room.get(item.subject_id)
        key = (group.class_ids[0], item.subject_id, kind)
        need[key] = need.get(key, 0) + 1
    for (class_id, subject_id, kind), count in need.items():
        available = rooms_by_kind.get(kind, 0)
        if count > available:
            name = subject_name_by_id.get(subject_id, subject_id)
            problems.append(
                f"{class_id}, «{name}»: {count} подгруппы должны заниматься одновременно, "
                f"а кабинеты типа «{KIND_BY_VALUE.get(kind.value, kind.value)}» "
                f"вмещают {available} за раз. Либо не делите этот предмет, "
                f"либо добавьте кабинет"
            )

    # По той же причине подгруппы обязаны вести РАЗНЫЕ учителя: они занимаются
    # в один и тот же час, и один человек в двух кабинетах не окажется.
    # Ошибка бытовая и очень частая: английский в школе ведёт один сильный
    # учитель, его и ставят на обе подгруппы — а расписание после этого не
    # существует вовсе. Без этой проверки завуч получал бы голое «решения нет»
    # (найдено 25.08.2026 на модели сельской школы: 11 таких строк).
    teacher_names = {t.id: t.name for t in teachers}
    who: dict[tuple[str, str, str], set] = {}
    for item in load:
        group = school.group(item.group_id)
        if group.part is None:
            continue
        key = (group.class_ids[0], item.subject_id, item.teacher_id)
        who.setdefault(key, set()).add(group.part)
    for (class_id, subject_id, teacher_id), parts in who.items():
        if len(parts) > 1:
            name = subject_name_by_id.get(subject_id, subject_id)
            problems.append(
                f"{class_id}, «{name}»: {teacher_names.get(teacher_id, teacher_id)} "
                f"назначен(а) сразу на подгруппы {', '.join(sorted(parts))}, "
                f"а они занимаются в один и тот же час. Назначьте на вторую "
                f"подгруппу другого учителя — или уберите деление, если предмет "
                f"идёт всем классом"
            )

    return school, problems


def check_norms(school: School) -> list[str]:
    """Предупреждения по санитарным нормам РБ.

    Не ошибки ввода: расписание составится и так. Но завуч должен знать,
    что нагрузка выходит за предельную — это его ответственность,
    а не дефект алгоритма.
    """
    warnings: list[str] = []
    if not school.norms.max_hours_per_week:
        return warnings
    for c in school.classes:
        # Подгруппы не удваивают нагрузку класса: пока одна половина на труде,
        # вторая тоже занята. В сетке это один слот, значит и час один.
        whole = sum(i.hours_per_week for i in school.load
                    if school.group(i.group_id).class_ids == [c.id]
                    and school.group(i.group_id).part is None)
        split_subjects = {i.subject_id: i.hours_per_week for i in school.load
                          if school.group(i.group_id).class_ids == [c.id]
                          and school.group(i.group_id).part is not None}
        hours = whole + sum(split_subjects.values())
        limit = school.norms.hours_limit(c.parallel, c.advanced)
        if limit and hours > limit:
            level = "с повышенным уровнем" if c.advanced else "базовый уровень"
            warnings.append(
                f"{c.name}: {hours} часов в неделю при предельной норме {limit} "
                f"({level}, типовой учебный план, постановление Минобразования № 75)"
            )

    # Физкультура: норма «не два дня подряд» (п. 94 ССЭТ) сама ограничивает
    # число часов. В пятидневку без двух дней подряд помещается максимум три
    # занятия — понедельник, среда, пятница. Класс с четырьмя часами (а такие
    # бывают: спортивно-педагогический профиль по типовому плану) нерешаем
    # арифметически.
    # Найдено 24.08.2026 на модели городской школы: единственный класс из 28
    # обрушал весь прогон. С 25.08.2026 солвер ослабляет норму ТОЧЕЧНО — только
    # в этом классе (см. lad/solve.py, pe_two_days), поэтому предупреждение
    # больше не про «не составится», а про «здесь норма будет нарушена».
    pe_name = (school.norms.pe_subject or "").lower()
    if pe_name and school.norms.pe_no_two_days_in_row:
        days = len([d for d, kind in school.day_kinds.items() if kind.value == "lessons"])
        max_days = (days + 1) // 2
        subject_names = {s.id: s.name.lower() for s in school.subjects}
        for c in school.classes:
            hours = sum(i.hours_per_week for i in school.load
                        if c.id in school.group(i.group_id).class_ids
                        and subject_names.get(i.subject_id, "").startswith(pe_name[:12]))
            if hours > max_days:
                warnings.append(
                    f"{c.name}: {hours} ч физкультуры в неделю, а норма «не два дня подряд» "
                    f"(п. 94 ССЭТ № 525) вмещает максимум {max_days} занятия при "
                    f"{days}-дневной неделе. Расписание составится — для этого класса "
                    f"норма будет посчитана мягко, — но в нём останется нарушение. "
                    f"Чтобы его не было, перенесите лишний час в шестой школьный день"
                )

    # Теснота сетки. Класс учится подряд с первого урока и без окон (HARD-8),
    # поэтому его часы должны лечь в сетку почти сплошняком. Когда занято
    # больше девяти десятых мест, свободы у солвера почти нет: любая норма
    # («физкультура не два дня подряд», «трудный предмет на краю дня») становится
    # трудновыполнимой, и поиск уходит в минуты и часы без результата.
    # Замерено 25.08.2026 на гимназии в 28 классов: при сетке в 7 уроков
    # и заполнении 94% расписание не нашлось за десять минут, при 8 уроках —
    # нашлось. Сказать надо ДО запуска, иначе завуч будет добавлять время там,
    # где нужно добавить урок в сетку.
    slots_per_week = len(school.lesson_slots())
    busy: dict[str, dict] = {}
    for item in school.load:
        for class_id in school.group(item.group_id).class_ids:
            # Подгруппы одного предмета идут в один слот, значит занимают
            # столько часов, сколько стоит у одной подгруппы, а не у обеих.
            per = busy.setdefault(class_id, {})
            per[item.subject_id] = max(per.get(item.subject_id, 0), item.hours_per_week)
    tight = sorted(((sum(per.values()), class_id) for class_id, per in busy.items()),
                   reverse=True)
    if slots_per_week and tight and tight[0][0] / slots_per_week > 0.9:
        filled, class_id = tight[0]
        crowded = sum(1 for hours, _ in tight if hours / slots_per_week > 0.9)
        warnings.append(
            f"Сетка тесная: у {class_id} {filled} часов на {slots_per_week} мест — "
            f"занято {filled / slots_per_week * 100:.0f}%"
            + (f", и таких классов {crowded}" if crowded > 1 else "")
            + ". Класс учится без окон, поэтому его уроки должны лечь почти "
            "сплошняком, и запаса на санитарные нормы не остаётся. Если расписание "
            "не сойдётся или будет искаться слишком долго — добавьте урок в сетку "
            "(«максимум уроков в день» слева), это надёжнее, чем ждать дольше"
        )

    # Та же норма, но для ШКОЛЫ целиком, а не для отдельного класса.
    # «Не два дня подряд» оставляет три дня из пяти, и в эти три дня должна
    # уместиться физкультура ВСЕЙ школы. Проверено 26.08.2026 на школе
    # в 24 класса: 72 урока физкультуры против 48 мест (три дня × восемь
    # уроков × два класса в зале) — расписания не существует, и солвер
    # доказывал это за 25 секунд, ничего не объясняя.
    if pe_name and school.norms.pe_no_two_days_in_row:
        gym_seats = sum(max(1, room.parallel_classes) for room in school.rooms
                        if room.kind == RoomKind.GYM)
        pe_hours = sum(i.hours_per_week for i in school.load
                       if subject_names.get(i.subject_id, "").startswith(pe_name[:12]))
        if gym_seats and pe_hours:
            fits = max_days * school.periods_per_day * gym_seats
            if pe_hours > fits:
                warnings.append(
                    f"Физкультуры в школе {pe_hours} ч в неделю, а норма «не два дня "
                    f"подряд» (п. 94 ССЭТ № 525) оставляет {max_days} дня из {days}. "
                    f"За эти дни спортзал вмещает {fits} уроков — на {pe_hours - fits} "
                    f"меньше, чем нужно. Расписания с этой нормой не существует. "
                    f"Выходы: переключить её на «мягко» на вкладке «Нормы», или "
                    f"указать в кабинетах, что в зале занимается больше классов сразу, "
                    f"или перенести часть часов в шестой школьный день"
                )

    # Вторая смена запрещена не везде (п. 92 ССЭТ № 525).
    forbidden = set(school.norms.second_shift_forbidden_parallels)
    advanced_forbidden = set(school.norms.second_shift_forbidden_if_advanced)
    for c in school.classes:
        if c.shift.value != 2:
            continue
        if c.parallel in forbidden or (c.advanced and c.parallel in advanced_forbidden):
            warnings.append(
                f"{c.name}: вторая смена запрещена в этой параллели (п. 92 ССЭТ № 525)"
            )
    return warnings




# ------------------------------------------------------- мастер первого запуска

PLAN_FILE = Path("data/plan_75.json")


def load_plan() -> dict:
    """Типовой учебный план: предмет → параллель → часов.

    Нужен, чтобы завуч не набивал нагрузку с нуля. Часы берутся из
    постановления Минобразования № 75, а не придумываются. Там, где в документе
    стоит дробь («1/2» — разное число часов по полугодиям), значение пустое:
    его вводит человек, потому что решение зависит от школы.
    """
    if not PLAN_FILE.exists():
        return {"subjects": []}
    return json.loads(PLAN_FILE.read_text(encoding="utf-8"))


def generate_classes(counts: dict[int, int], sizes: dict[int, int] | None = None
                     ) -> pd.DataFrame:
    """Из «в 5-й параллели 3 класса» сделать строки 5А, 5Б, 5В."""
    letters = "АБВГДЕЖЗИК"
    sizes = sizes or {}
    rows = []
    for parallel in sorted(counts):
        for n in range(counts[parallel]):
            rows.append({
                "класс": f"{parallel}{letters[n]}",
                "учеников": sizes.get(parallel, 24),
                "повышенный уровень": False,
            })
    return pd.DataFrame(rows) if rows else blank_tables()["classes"].iloc[0:0]


def parallels_of(classes: pd.DataFrame) -> list[int]:
    """Какие годы обучения представлены в таблице классов."""
    found = {parse_class_name(n)[0] for n in classes.get("класс", [])}
    return sorted(p for p in found if p)


def generate_subjects(parallels: list[int], plan: dict | None = None) -> pd.DataFrame:
    """Предметы, которые изучаются в этих параллелях, — из типового плана."""
    plan = plan or load_plan()
    rows = []
    for subject in plan.get("subjects", []):
        hours = subject.get("hours", {})
        if any(str(p) in hours for p in parallels):
            kind = subject.get("room", "обычный")
            rows.append({
                "предмет": subject["name"],
                "кабинет": kind,
                # Строгими отмечаются только те, кого без своего кабинета
                # не провести. Физика, химия, биология сюда не входят.
                "только в нём": ROOM_KINDS.get(kind) in STRICT_ROOM_KINDS,
            })
    return pd.DataFrame(rows) if rows else blank_tables()["subjects"].iloc[0:0]


def generate_load(classes: pd.DataFrame, plan: dict | None = None,
                  teacher: str = "") -> tuple[pd.DataFrame, list[str]]:
    """Черновик нагрузки по типовому плану.

    Возвращает таблицу и список предметов, часы которых в документе заданы
    дробью по полугодиям — их завуч заполняет сам. Учитель везде пустой:
    кто что ведёт, знает только школа.
    """
    plan = plan or load_plan()
    rows, unknown = [], []
    for _, row in classes.iterrows():
        class_name = str(row.get("класс") or "").strip()
        number, _ = parse_class_name(class_name)
        if not class_name or number is None:
            continue
        parallel = str(number)
        for subject in plan.get("subjects", []):
            hours = subject.get("hours", {})
            if parallel not in hours:
                continue
            value = hours[parallel]
            if value is None:
                note = f"{subject['name']} ({parallel} кл.)"
                if note not in unknown:
                    unknown.append(note)
                continue
            parts = ("1", "2") if subject.get("splits") else ("",)
            split_rooms = subject.get("split_rooms") or []
            for n, part in enumerate(parts):
                rows.append({
                    "класс": class_name,
                    "предмет": subject["name"],
                    "учитель": teacher,
                    "часов": value,
                    "подгруппа": part,
                    "уровень": "базовый",
                    "тип": "урок",
                    # у труда подгруппы идут в разные кабинеты: мастерская
                    # и кабинет обслуживающего труда
                    "кабинет": split_rooms[n] if n < len(split_rooms) else NONE_CHOICE,
                })
    table = pd.DataFrame(rows) if rows else blank_tables()["load"].iloc[0:0]
    return table, unknown


def generate_rooms(regular: int, special: dict[str, int]) -> pd.DataFrame:
    """Кабинетный фонд: обычные нумеруются подряд, спецкабинеты — по названию."""
    rows = [{"кабинет": str(101 + n), "тип": "обычный", "мест": 30, "классов сразу": 1}
            for n in range(regular)]
    for kind, count in special.items():
        for n in range(count):
            suffix = f" {n + 1}" if count > 1 else ""
            rows.append({"кабинет": f"{kind.capitalize()}{suffix}", "тип": kind, "мест": 30,
                         # В спортзале обычно занимаются два класса сразу,
                         # у каждого свой учитель. Ставим двойку по умолчанию:
                         # так школа описывается верно без лишних вопросов,
                         # а если зал маленький — цифру видно и её легко исправить.
                         "классов сразу": 2 if kind == "спортзал" else 1})
    return pd.DataFrame(rows) if rows else blank_tables()["rooms"].iloc[0:0]


# ------------------------------------------------------ сверка с учебным планом

def compare_with_plan(school: School, plan: dict | None = None) -> pd.DataFrame:
    """Сравнить введённую нагрузку с типовым учебным планом.

    Отвечает на вопрос «какие уроки положены этому классу и сколько часов».
    Без такой сверки забытый предмет обнаружится только в сентябре: солвер
    честно составит расписание из того, что дали, и промолчит про физику,
    которой в восьмом классе нет.

    Что сверяется:
      • предмет из плана не введён вовсе;
      • часов меньше или больше, чем в плане;
      • введён предмет, которого в типовом плане для этой параллели нет
        (это не ошибка — так выглядит компонент учреждения образования,
        но завуч должен видеть, что это его решение, а не норма).

    Подгруппы считаются один раз: пока одна половина класса на труде, вторая
    тоже занята, в сетке это один час.
    """
    plan = plan or load_plan()
    by_name = {s["name"]: s for s in plan.get("subjects", [])}
    subject_names = {s.id: s.name for s in school.subjects}

    rows = []
    for c in school.classes:
        parallel = str(c.parallel)

        # что введено: предмет → (часы, уровень, факультатив ли)
        entered: dict[str, dict] = {}
        for item in school.load:
            group = school.group(item.group_id)
            if c.id not in group.class_ids:
                continue
            name = subject_names.get(item.subject_id, "?")
            slot = entered.setdefault(name, {"hours": 0, "level": item.level,
                                             "elective": item.kind != LessonKind.REGULAR,
                                             "parts": set()})
            # подгруппы одного предмета занимают один и тот же час
            part = group.part or ""
            if part not in slot["parts"]:
                slot["parts"].add(part)
                if len(slot["parts"]) == 1:
                    slot["hours"] += item.hours_per_week
            if item.level != Level.BASE:
                slot["level"] = item.level

        for name, subject in by_name.items():
            advanced = entered.get(name, {}).get("level", Level.BASE) != Level.BASE
            source = subject.get("hours_advanced", {}) if advanced else {}
            due = source.get(parallel) if parallel in source else subject.get("hours", {}).get(parallel)
            got = entered.get(name, {}).get("hours")

            if due is None and got is None:
                continue
            if due is None:
                if entered.get(name, {}).get("elective"):
                    status = "факультатив — вне типового плана"
                else:
                    status = "нет в типовом плане для этой параллели"
            elif got is None:
                status = "НЕ ВВЕДЁН"
            elif got == due:
                status = "✓"
            else:
                status = f"расхождение: {got - due:+d} ч"

            rows.append({
                "класс": c.name,
                "предмет": name,
                "уровень": "повышенный" if advanced else "базовый",
                # Числа остаются числами: колонка со смесью int и «—» ломает
                # сериализацию таблицы в интерфейсе (pyarrow не берёт смешанный тип).
                "положено": due,
                "введено": got,
                "статус": status,
            })

        # предметы, которых нет в справочнике плана вовсе
        for name in entered:
            if name not in by_name:
                rows.append({
                    "класс": c.name, "предмет": name,
                    "уровень": "базовый", "положено": None,
                    "введено": entered[name]["hours"],
                    "статус": "нет в справочнике плана",
                })

    return pd.DataFrame(rows)


def plan_summary(school: School, plan: dict | None = None) -> pd.DataFrame:
    """Итог по классам: сколько часов положено, введено и какова предельная норма."""
    table = compare_with_plan(school, plan)
    rows = []
    for c in school.classes:
        part = table[table["класс"] == c.name]
        due = int(pd.to_numeric(part["положено"], errors="coerce").fillna(0).sum())
        got = int(pd.to_numeric(part["введено"], errors="coerce").fillna(0).sum())
        limit = school.norms.hours_limit(c.parallel, c.advanced)
        problems = int((part["статус"] != "✓").sum())
        rows.append({
            "класс": c.name,
            "профиль": "повышенный уровень" if c.advanced else "базовый",
            "по плану": due,
            "введено": got,
            "предельная норма": limit if limit else "—",
            "расхождений": problems,
            "сверх нормы": "⚠️ да" if limit and got > limit else "нет",
        })
    return pd.DataFrame(rows)


def apply_profile(load: pd.DataFrame, class_name: str, subjects: list[str],
                  plan: dict | None = None) -> tuple[pd.DataFrame, list[str]]:
    """Сделать предметы класса профильными: повышенный уровень и часы по плану.

    Профиль X–XI — это и есть набор предметов на повышенном уровне. В типовом
    плане их часы заданы диапазоном: математика «4–6», где 4 — базовый уровень,
    6 — повышенный. Здесь выставляется верхняя граница.

    Возвращает изменённую таблицу и список того, что поменялось, — чтобы завуч
    видел, а не гадал.
    """
    plan = plan or load_plan()
    by_name = {s["name"]: s for s in plan.get("subjects", [])}
    parallel = str(parse_class_name(class_name)[0])
    load = load.copy()
    for column, default in (("уровень", "базовый"), ("тип", "урок")):
        if column not in load.columns:
            load[column] = default

    changes = []
    for name in subjects:
        subject = by_name.get(name)
        if not subject:
            continue
        hours = (subject.get("hours_advanced") or {}).get(parallel)
        mask = (load["класс"] == class_name) & (load["предмет"] == name)
        if not mask.any():
            changes.append(f"«{name}» — в нагрузке класса нет, добавьте строку")
            continue
        was = int(load.loc[mask, "часов"].iloc[0])
        load.loc[mask, "уровень"] = "повышенный"
        if hours:
            load.loc[mask, "часов"] = hours
            if hours != was:
                changes.append(f"«{name}»: {was} → {hours} ч (повышенный уровень)")
            else:
                changes.append(f"«{name}»: повышенный уровень, часы прежние ({hours})")
        else:
            changes.append(f"«{name}»: повышенный уровень; часов для этой параллели "
                           "в плане нет, проставьте сами")
    return load, changes


# ------------------------------------------------------------ порядок ввода

# Порядок не произвольный: каждый следующий шаг опирается на предыдущие.
# Нагрузку нельзя заполнить, пока нет классов, предметов и учителей, —
# в ней выбирают из них. Пожелания нельзя, пока нет учителей.
INPUT_STEPS = [
    {"key": "classes", "title": "Классы", "needs": [],
     "why": "С чего начинается школа. Год обучения система берёт из названия: «7Б» → 7. "
            "От него зависят предельная нагрузка и шкала трудности предметов.",
     "empty": "Без классов расписание составлять не для кого."},
    {"key": "subjects", "title": "Предметы", "needs": ["classes"],
     "why": "Список предметов школы. Здесь же указывается, какому предмету нужен "
            "специальный кабинет: физике — свой, физкультуре — спортзал.",
     "empty": "Без предметов нечего ставить в сетку."},
    {"key": "teachers", "title": "Учителя", "needs": [],
     "why": "Список тех, кто ведёт уроки. Методический день — день недели без уроков, "
            "если он у учителя есть.",
     "empty": "Без учителей нагрузку не на кого расписать."},
    {"key": "rooms", "title": "Кабинеты", "needs": [],
     "why": "Кабинетный фонд. Солвер следит, чтобы два класса не оказались в одном "
            "кабинете и чтобы физика шла в кабинет физики.",
     "empty": "Без кабинетов проверка занятости помещений не работает."},
    {"key": "load", "title": "Нагрузка", "needs": ["classes", "subjects", "teachers"],
     "why": "Главная таблица: кто какой предмет ведёт в каком классе и сколько часов "
            "в неделю. Из неё солвер и строит расписание.",
     "empty": "Это единственная таблица, без которой ничего не получится."},
    {"key": "wishes", "title": "Пожелания", "needs": ["teachers"], "optional": True,
     "why": "Когда учитель не может работать. Заполняется по желанию: без пожеланий "
            "расписание составится, просто не будет учитывать личные обстоятельства.",
     "empty": "Не заполнено — солвер считает, что все учителя свободны всегда."},
]


# ------------------------------------------------------- назначение учителей
#
# Заполнять нагрузку построчно нельзя: у городской школы это 500 строк, и класс,
# предмет и часы в них УЖЕ известны из типового плана — вручную вписывают только
# учителя. Поэтому ввод перевёрнут: выбираем предмет, а внутри него каждому
# учителю отмечаем его классы. Математика в школе на 28 классов — это 7 учителей
# вместо 28 строк.


def slot_label(class_name: str, part) -> str:
    """«5А» или «5А (1)» — как строка нагрузки выглядит в списке классов."""
    part = str(part or "").strip()
    return f"{class_name} ({part})" if part and part.lower() != "nan" else class_name


def subject_slots(load: pd.DataFrame, subject: str) -> pd.DataFrame:
    """Все места этого предмета: класс, подгруппа, часы и кто назначен."""
    if load is None or "предмет" not in load:
        return pd.DataFrame(columns=["метка", "класс", "подгруппа", "часов", "учитель"])
    rows = load[load["предмет"].astype(str) == subject]
    out = []
    for _, row in rows.iterrows():
        out.append({
            "метка": slot_label(row.get("класс"), row.get("подгруппа")),
            "класс": str(row.get("класс") or ""),
            "подгруппа": str(row.get("подгруппа") or "").strip(),
            "часов": int(row.get("часов") or 0),
            "учитель": optional(row.get("учитель")),
        })
    return pd.DataFrame(out)


def subject_progress(load: pd.DataFrame) -> pd.DataFrame:
    """По каждому предмету: сколько мест закрыто учителями, а сколько нет."""
    if load is None or "предмет" not in load or not len(load):
        return pd.DataFrame(columns=["предмет", "мест", "назначено", "часов"])
    rows = []
    for subject, group in load.groupby(load["предмет"].astype(str)):
        assigned = sum(1 for v in group["учитель"] if optional(v))
        rows.append({"предмет": subject, "мест": len(group), "назначено": assigned,
                     "часов": int(group["часов"].fillna(0).sum())})
    return pd.DataFrame(rows).sort_values(["назначено", "предмет"]).reset_index(drop=True)


def assign_teacher(load: pd.DataFrame, subject: str, teacher: str,
                   labels: list[str]) -> pd.DataFrame:
    """Закрепить за учителем ровно эти классы по этому предмету.

    Снятая галочка освобождает место: если класс был за учителем, а в списке
    его больше нет, поле учителя очищается. Иначе завуч не смог бы ничего
    переиграть, не открывая большую таблицу.
    """
    load = load.copy()
    chosen = set(labels)
    for index, row in load.iterrows():
        if str(row.get("предмет") or "") != subject:
            continue
        label = slot_label(row.get("класс"), row.get("подгруппа"))
        current = optional(row.get("учитель"))
        if label in chosen:
            load.at[index, "учитель"] = teacher
        elif current == teacher:
            load.at[index, "учитель"] = ""
    return load


def spread_evenly(load: pd.DataFrame, subject: str, teachers: list[str]) -> pd.DataFrame:
    """Раздать незакрытые классы предмета между учителями поровну по часам.

    Это черновик, а не решение за завуча: кто именно ведёт 7«Б», знает только
    школа. Но когда у математики 28 классов и семь преподавателей, разложить
    их по одному вручную — полчаса кликов, а поправить пару строк после
    автораздачи — минута.

    Подгруппы одного класса намеренно достаются РАЗНЫМ учителям: они
    занимаются одновременно, один человек в двух местах быть не может.
    """
    load = load.copy()
    if not teachers:
        return load
    hours = teacher_hours(load)
    taken: dict[str, set[str]] = {}
    for _, row in load.iterrows():
        who = optional(row.get("учитель"))
        if who:
            taken.setdefault(who, set()).add(
                slot_label(row.get("класс"), row.get("подгруппа")).split(" (")[0])

    free = [(i, row) for i, row in load.iterrows()
            if str(row.get("предмет") or "") == subject and not optional(row.get("учитель"))]
    # Сначала места с большим числом часов: их труднее пристроить потом.
    free.sort(key=lambda pair: -int(pair[1].get("часов") or 0))

    for index, row in free:
        class_name = str(row.get("класс") or "")
        part = str(row.get("подгруппа") or "").strip()
        candidates = [t for t in teachers
                      if not (part and class_name in taken.get(t, set()))]
        if not candidates:
            continue
        who = min(candidates, key=lambda t: hours.get(t, 0))
        load.at[index, "учитель"] = who
        hours[who] = hours.get(who, 0) + int(row.get("часов") or 0)
        taken.setdefault(who, set()).add(class_name)
    return load


def plan_hours(subject: str, parallel: int, plan: dict | None = None) -> int | None:
    """Часы предмета в этой параллели по типовому плану, если он их задаёт."""
    plan = plan or load_plan()
    for item in plan.get("subjects", []):
        if str(item.get("name")) == subject:
            value = (item.get("hours") or {}).get(str(parallel))
            return int(value) if value else None
    return None


def add_subject_slots(load: pd.DataFrame, subject: str, class_names: list[str],
                      hours: int | None = None, plan: dict | None = None) -> tuple[pd.DataFrame, list[str]]:
    """Завести предмет там, где его ещё нет: новые строки нагрузки.

    Нужно, потому что типовой план — не приговор. Школа может дать астрономию
    десятому классу или ввести факультатив, которого в документе нет вовсе,
    и упираться в «в списке такого класса нет» она не должна.

    Часы берутся из плана для этой параллели; если план молчит — из аргумента.
    Делимый предмет заводится двумя строками сразу: подгруппы «1» и «2».
    """
    plan = plan or load_plan()
    load = load.copy()
    divided = subject in split_subjects(load)
    if not divided:
        for item in plan.get("subjects", []):
            if str(item.get("name")) == subject and item.get("splits"):
                divided = True

    existing = {(str(r.get("класс")), str(r.get("подгруппа") or "").strip())
                for _, r in load.iterrows() if str(r.get("предмет")) == subject}
    room = next((str(item.get("room") or "")
                 for item in plan.get("subjects", [])
                 if str(item.get("name")) == subject), "")
    rows, skipped = [], []
    for class_name in class_names:
        parallel, _ = parse_class_name(class_name)
        value = hours or (plan_hours(subject, parallel, plan) if parallel else None)
        if not value:
            skipped.append(class_name)
            continue
        for part in (("1", "2") if divided else ("",)):
            if (class_name, part) in existing:
                continue
            rows.append({
                "класс": class_name, "предмет": subject, "учитель": "",
                "часов": int(value), "подгруппа": part,
                "уровень": "базовый", "тип": "урок",
                "кабинет": room if room in ROOM_KINDS else NONE_CHOICE,
            })
    if rows:
        load = pd.concat([load, pd.DataFrame(rows)], ignore_index=True)
    return load, skipped


def teacher_hours(load: pd.DataFrame) -> dict[str, int]:
    """Сколько часов в неделю набрал каждый учитель — чтобы не перегрузить."""
    hours: dict[str, int] = {}
    if load is None or "учитель" not in load:
        return hours
    for _, row in load.iterrows():
        who = optional(row.get("учитель"))
        if who:
            hours[who] = hours.get(who, 0) + int(row.get("часов") or 0)
    return hours


def split_subjects(load: pd.DataFrame) -> set[str]:
    """Предметы, где класс делится на подгруппы: там нужны два учителя на класс."""
    if load is None or "подгруппа" not in load:
        return set()
    marked = load[load["подгруппа"].astype(str).str.strip().isin(["1", "2"])]
    return set(marked["предмет"].astype(str))


def input_status(tables: dict[str, pd.DataFrame], wishes: dict | None = None) -> list[dict]:
    """Что уже введено, а что нет, и в каком порядке продолжать.

    Завуч не должен догадываться, чего не хватает: система знает это сама.
    """
    wishes = wishes or {}
    counts = {}
    for step in INPUT_STEPS:
        key = step["key"]
        if key == "wishes":
            counts[key] = sum(1 for w in wishes.values() if w.get("hard") or w.get("soft"))
        else:
            table = tables.get(key)
            counts[key] = 0 if table is None else len(table.dropna(how="all"))

    result = []
    for step in INPUT_STEPS:
        missing = [s["title"] for s in INPUT_STEPS
                   if s["key"] in step["needs"] and not counts.get(s["key"])]
        result.append({
            **step,
            "count": counts[step["key"]],
            "done": bool(counts[step["key"]]),
            "blocked_by": missing,
        })
    return result


def next_step(status: list[dict]) -> dict | None:
    """Первый незаполненный обязательный шаг — то, что делать дальше."""
    for step in status:
        if not step["done"] and not step.get("optional"):
            return step
    return None
