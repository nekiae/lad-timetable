"""Синтетика для проверки солвера: параллель V, три класса.

ЭТО НЕ ДЕМО-ДАННЫЕ. Настоящее демо строится на реальном расписании школы (§8.1).
Здесь проверяется, что солвер шевелится и что нормы применимы на правдоподобных
данных, а не на выдуманных.

Нагрузка взята из ПЕРВОИСТОЧНИКА — типовой учебный план базовой школы,
постановление Минобразования РБ от 23.04.2025 № 75, колонка V класса
(вариант школы с обучением на русском языке). Сумма — 27 часов, что совпадает
с обязательным объёмом учебной нагрузки в том же документе.

Почему это важно: на выдуманном наборе предметов нормы п. 94 ССЭТ дают
INFEASIBLE — в нём просто нет «лёгких» предметов, которыми можно закрыть
первые и последние уроки дня. Проверено 23.08.2026: набор из четырёх трудных
предметов и физкультуры нерешаем в принципе, и это свойство данных, а не бага.
"""

from .model import (
    LoadItem, Room, RoomKind, School, SchoolClass, StudyGroup, Subject, Teacher,
)

# Предмет → (часов в неделю в V классе, нужен ли спецкабинет, делится ли на подгруппы)
PLAN_V = [
    ("Белорусский язык", 3, RoomKind.REGULAR, False),
    ("Белорусская литература", 2, RoomKind.REGULAR, False),
    ("Русский язык", 3, RoomKind.REGULAR, False),
    ("Русская литература", 2, RoomKind.REGULAR, False),
    ("Иностранный язык", 3, RoomKind.REGULAR, True),
    ("Математика", 5, RoomKind.REGULAR, False),
    ("Человек и мир", 1, RoomKind.REGULAR, False),
    ("Всемирная история", 2, RoomKind.REGULAR, False),
    ("Искусство (отечественная и мировая художественная культура)", 1, RoomKind.REGULAR, False),
    ("Трудовое обучение", 1, RoomKind.WORKSHOP_TECH, True),
    ("Физическая культура и здоровье", 3, RoomKind.GYM, False),
    ("Основы безопасности жизнедеятельности", 1, RoomKind.REGULAR, False),
]

# Сколько учителей ведёт предмет во всей параллели. Считается по ставке:
# 3 класса × 3 часа иностранного × 2 подгруппы = 18 часов — это два учителя.
TEACHERS_PER_SUBJECT = {"Иностранный язык": 2, "Трудовое обучение": 2}


def build(letters: str = "АБВ") -> School:
    classes = [SchoolClass(id=f"5{L}", parallel=5, letter=L, size=24) for L in letters]

    subjects, teachers, groups, load = [], [], [], []
    for n, (name, hours, room, splits) in enumerate(PLAN_V):
        subject = Subject(id=f"s{n}", name=name, required_room=room, splits_class=splits)
        subjects.append(subject)

        count = TEACHERS_PER_SUBJECT.get(name, 1)
        subject_teachers = [
            Teacher(id=f"t{n}_{k}", name=f"{name[:12]}, преп. {k + 1}", subject_ids=[subject.id])
            for k in range(count)
        ]
        teachers += subject_teachers

        for c_index, c in enumerate(classes):
            if not splits:
                gid = c.id
                if not any(g.id == gid for g in groups):
                    groups.append(StudyGroup(id=gid, class_ids=[c.id], size=c.size))
                load.append(LoadItem(group_id=gid, subject_id=subject.id,
                                     teacher_id=subject_teachers[0].id, hours_per_week=hours))
            else:
                # Деление на подгруппы: обе половины класса учатся одновременно
                # у разных учителей (HARD-9 держит их в одном слоте).
                for part in ("1", "2"):
                    gid = f"{c.id}·{name}·{part}"
                    groups.append(StudyGroup(id=gid, class_ids=[c.id], part=part, size=c.size // 2))
                    teacher = subject_teachers[(c_index + int(part)) % len(subject_teachers)]
                    load.append(LoadItem(group_id=gid, subject_id=subject.id,
                                         teacher_id=teacher.id, hours_per_week=hours))

    rooms = [Room(id=f"{100 + i}", kind=RoomKind.REGULAR, capacity=30) for i in range(len(classes) + 2)]
    rooms += [
        Room(id="Спортзал", kind=RoomKind.GYM, capacity=30),
        Room(id="Мастерская 1", kind=RoomKind.WORKSHOP_TECH, capacity=15),
        Room(id="Мастерская 2", kind=RoomKind.WORKSHOP_TECH, capacity=15),
    ]

    return School(name="Школа (синтетика по типовому плану № 75)", classes=classes,
                  groups=groups, teachers=teachers, subjects=subjects, rooms=rooms,
                  load=load, periods_per_day=8)
