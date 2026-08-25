"""Схема данных ЛАД.

Спроектирована под всё, что описано в docs/domain.md — включая то, что солвер
на этой неделе не ограничивает. Причина: схему потом не переделаешь, а поле,
которое лежит пустым, ничего не стоит.

Главное решение схемы: атомарная единица расписания — не класс, а УЧЕБНАЯ ГРУППА.
Класс целиком — частный случай группы. Иначе не описать деления (иностранный,
труд, информатика) и межклассные профильные группы X–XI.
"""

from dataclasses import dataclass, field
from enum import Enum


class Shift(int, Enum):
    """Смена. Школа может быть односменной — тогда везде FIRST."""

    FIRST = 1
    SECOND = 2


class DayKind(str, Enum):
    """Тип учебного дня.

    В РБ шестидневка не означает шесть дней уроков: уроки идут пять дней,
    суббота — «шестой школьный день» с факультативами, кружками и спортом.
    Поэтому день недели сам по себе не говорит, можно ли ставить туда урок.
    """

    LESSONS = "lessons"  # обычный учебный день
    SIXTH_DAY = "sixth_day"  # шестой школьный день: уроков нет


class LessonKind(str, Enum):
    """Тип занятия.

    Факультативы и стимулирующие/поддерживающие занятия не оптимизируются
    на MVP, но ЗАНИМАЮТ учителя и кабинет. Если их не внести, солвер будет
    считать учителя свободным, когда он занят.
    """

    REGULAR = "regular"  # урок по учебному плану
    ELECTIVE = "elective"  # факультативное занятие
    SUPPORT = "support"  # стимулирующее / поддерживающее
    CLASS_HOUR = "class_hour"  # классный / информационный час


class Level(str, Enum):
    """Уровень изучения предмета.

    Для солвера математика на базовом и на повышенном уровне — РАЗНЫЕ предметы:
    разные часы, разные группы, часто разные учителя.
    """

    BASE = "base"
    ADVANCED = "advanced"  # повышенный
    DEEP = "deep"  # углублённый


class RoomKind(str, Enum):
    """Тип кабинета. Спецкабинет выводится из предмета через маппинг."""

    REGULAR = "regular"
    PHYSICS = "physics"
    CHEMISTRY = "chemistry"
    BIOLOGY = "biology"
    COMPUTER = "computer"
    GYM = "gym"
    WORKSHOP_TECH = "workshop_tech"  # мастерская, техтруд
    WORKSHOP_SERVICE = "workshop_service"  # обслуживающий труд
    MILITARY = "military"  # кабинет допризывной подготовки
    ASSEMBLY = "assembly"


@dataclass(frozen=True)
class Slot:
    """Клетка сетки: день × номер урока × смена.

    Номер урока — порядковый, НЕ время. Время подтягивается из BellSchedule,
    потому что расписание звонков уникально для каждой школы.
    """

    day: int  # 1 = понедельник … 6 = суббота
    period: int  # 1..8, порядковый номер урока
    shift: Shift = Shift.FIRST

    def __str__(self) -> str:
        return f"д{self.day}/у{self.period}" + ("" if self.shift == Shift.FIRST else "/см2")


@dataclass
class BellSchedule:
    """Расписание звонков — входные данные школы, не константа.

    Может отличаться для смен, для начальной школы, для субботы.
    Ключ periods: номер урока → (начало, конец) в формате "08:00".
    """

    name: str
    periods: dict[int, tuple[str, str]]
    shift: Shift = Shift.FIRST


@dataclass
class Subject:
    """Предмет.

    Справочник строится ИЗ ДАННЫХ ШКОЛЫ (любые написания), а этот объект —
    результат нормализации через data/subjects_map.json.
    """

    id: str
    name: str
    level: Level = Level.BASE
    # Ранг трудности по шкале РБ. None = не подтверждено первоисточником.
    # НЕ подставлять российскую шкалу: она другая (см. RU-TRAP в docs/domain.md).
    difficulty: int | None = None
    required_room: RoomKind = RoomKind.REGULAR
    # Обязателен ли этот кабинет — или он лишь желателен.
    #
    # Разница взята из того, как школа живёт на самом деле. Физкультуру нельзя
    # провести в классной комнате, информатику — без компьютеров, труд —
    # без станков: там кабинет обязателен. А физика, химия и биология сидят
    # в своём кабинете, только когда идёт лабораторная; в остальное время урок
    # спокойно идёт в обычном классе, и два класса меняются кабинетами
    # по обстоятельствам.
    #
    # Пока привязка считалась железной, школа с одним кабинетом физики на
    # 24 класса не описывалась вовсе: 40 часов физики при 40 уроках в неделе
    # требуют, чтобы кабинет был занят каждый урок без просвета. Расписания
    # для такого не существует — солвер это доказывал за 26 секунд.
    room_strict: bool = True

    @property
    def room_pool(self) -> "list[RoomKind]":
        """Кабинеты, где урок может идти, — в порядке предпочтения.

        Для строгого предмета это один тип. Для нестрогого — свой кабинет,
        а если занят, обычный.
        """
        if self.required_room == RoomKind.REGULAR or self.room_strict:
            return [self.required_room]
        return [self.required_room, RoomKind.REGULAR]

    # Требует ли деления класса на группы (иностранный, труд, информатика).
    splits_class: bool = False


@dataclass
class SchoolClass:
    """Класс: параллель + литера."""

    id: str
    parallel: int  # 5..11
    letter: str
    size: int = 0
    shift: Shift = Shift.FIRST
    # Язык обучения: в одной школе бывают классы с русским и белорусским.
    language: str = "ru"
    profile: str | None = None  # профиль X–XI, если есть
    # Изучаются ли в классе отдельные предметы на повышенном уровне.
    # Меняет предельную недельную нагрузку (типовой учебный план № 75, сноска 6)
    # и запрет второй смены для VIII классов (п. 92 ССЭТ № 525).
    advanced: bool = False

    @property
    def name(self) -> str:
        return f"{self.parallel}{self.letter}"


@dataclass
class StudyGroup:
    """Учебная группа — то, что реально садится на урок.

    Три случая:
      1. весь класс           → class_ids = ["7А"], part = None
      2. подгруппа класса     → class_ids = ["7А"], part = "1" | "юноши" | ...
      3. межклассная группа   → class_ids = ["10А", "10Б"]  (профиль, факультатив)

    Правило занятости: две группы одного класса могут стоять в одном слоте
    (деление), группа и полный класс — не могут.
    """

    id: str
    class_ids: list[str]
    part: str | None = None
    size: int = 0

    @property
    def is_whole_class(self) -> bool:
        return self.part is None and len(self.class_ids) == 1


@dataclass
class Teacher:
    """Учитель."""

    id: str
    name: str
    subject_ids: list[str] = field(default_factory=list)
    # Слоты, в которые учитель НЕ МОЖЕТ работать (ставка, личные обстоятельства).
    # Жёсткий запрет: солвер туда урок не поставит никогда.
    unavailable: set[Slot] = field(default_factory=set)
    # Слоты, которые учителю НЕЖЕЛАТЕЛЬНЫ. Мягкое пожелание: солвер старается
    # не ставить, но поставит, если иначе расписание не сходится. Разделение
    # принципиальное — если всё сваливать в unavailable, задача станет
    # невыполнимой из-за пожеланий, которые на самом деле обсуждаемы.
    disliked: set[Slot] = field(default_factory=set)
    # Методический день — день недели без уроков. Реальная практика РБ.
    method_day: int | None = None
    # Совместитель: работает и в другой школе. На MVP не ограничиваем,
    # но флаг несём, чтобы честно назвать границу модели.
    is_external: bool = False
    home_room_id: str | None = None  # кабинетная система: свой кабинет
    class_teacher_of: str | None = None  # классное руководство


@dataclass
class Room:
    """Кабинет."""

    id: str
    kind: RoomKind = RoomKind.REGULAR
    capacity: int = 0  # мест для учеников
    building: str = "1"  # корпус: переход между зданиями требует времени
    # Сколько классов помещается в этом кабинете ОДНОВРЕМЕННО.
    #
    # Почти везде один, но спортзал — исключение, и не редкое: в зале ставят
    # два класса сразу, каждый со своим учителем. «Это всегда так», сказал
    # завуч — и без этого школа не описывается вовсе. Считаем: 24 класса
    # по 3 часа физкультуры дают 72 урока в неделю, а пятидневка вмещает 40.
    # Один зал такую школу не обслужит, два класса разом — обслужит.
    #
    # Заводить вместо этого два кабинета «Спортзал А» и «Спортзал Б» можно,
    # но это ложь в данных: зал один, и завуч, увидев в отчёте два, решит,
    # что система его не поняла.
    parallel_classes: int = 1


@dataclass
class LoadItem:
    """Строка нагрузки — ГЛАВНЫЙ вход солвера.

    «Группа G изучает предмет S у учителя T столько-то часов в неделю».
    При реверс-инжиниринге выводится подсчётом по реальному расписанию.
    """

    group_id: str
    subject_id: str
    teacher_id: str
    hours_per_week: int
    kind: LessonKind = LessonKind.REGULAR
    # Базовый или повышенный уровень. В X–XI это меняет часы: математика
    # 4 против 6, физика 2 против 4. Профиль класса — это и есть набор
    # предметов, выбранных на повышенном уровне.
    level: Level = Level.BASE
    room_id: str | None = None  # если кабинет жёстко закреплён
    # Тип кабинета именно для этой строки — переопределяет тип, заданный предметом.
    # Нужен для деления, где подгруппы идут в РАЗНЫЕ кабинеты: труд у мальчиков
    # в мастерской, у девочек в кабинете обслуживающего труда. Предмет один
    # (иначе подгруппы не встанут синхронно), а кабинеты разные.
    room_kind: "RoomKind | None" = None


@dataclass
class Lesson:
    """Один поставленный урок — единица выхода солвера и элемент schedule.json."""

    slot: Slot
    group_id: str
    subject_id: str
    teacher_id: str
    room_id: str | None = None
    kind: LessonKind = LessonKind.REGULAR


@dataclass
class Norms:
    """Санитарные нормы — ВНЕШНИЙ КОНФИГ, а не константы в коде.

    Все поля по умолчанию пусты = «не подтверждено первоисточником».
    Ограничение, поле которого пусто, солвером НЕ ПРИМЕНЯЕТСЯ — вместо того,
    чтобы применяться с выдуманной цифрой. Заполняется из data/sanpin_by.json.

    Источники (проверено 23.08.2026):
      • СанПиН РБ № 206 от 27.12.2012 — шкала трудности, равномерность (п. 88.2)
      • ССЭТ, постановление Совмина № 525 от 07.08.2019 (ред. 12.07.2024) —
        режим занятий, пик работоспособности, физкультура, трудные предметы,
        сдвоенные уроки, смены (пп. 65, 67, 92, 93, 94, приложения 12 и 16)
      • Типовые учебные планы, постановление Минобразования № 75 от 23.04.2025 —
        предельная недельная нагрузка
    """

    max_hours_per_week: dict[int, int] = field(default_factory=dict)  # параллель → часов
    # То же для классов, где отдельные предметы изучаются на повышенном уровне.
    max_hours_per_week_advanced: dict[int, int] = field(default_factory=dict)
    max_lessons_per_day: dict[int, int] = field(default_factory=dict)
    lesson_minutes: int | None = None
    max_tests_per_day: int | None = None
    double_lessons_allowed: str | bool | None = None
    # Ранговая шкала трудности: название предмета → параллель → балл.
    # Балл зависит от года обучения: математика в V классе 8, в X–XI уже 12
    # (приложение 6 к СанПиН РБ). Поэтому это словарь словарей, а не одно число.
    difficulty_scale: dict[str, dict[int, int]] = field(default_factory=dict)

    # --- п. 94 ССЭТ: дни наибольшей работоспособности.
    # «Максимальная учебная нагрузка должна быть во вторник и (или) среду —
    # в I–IV классах, вторник, среду и (или) пятницу — в V–XI классах».
    peak_days_1_4: list[int] = field(default_factory=list)
    peak_days_5_11: list[int] = field(default_factory=list)

    # --- п. 94 ССЭТ: физкультура.
    # «Не допускается проведение… в течение двух дней подряд в одном классе
    # и более одного раза в неделю первыми или последними учебными занятиями».
    pe_subject: str | None = None
    pe_no_two_days_in_row: bool = False
    pe_max_first_or_last: int | None = None

    # --- п. 94 ССЭТ: предметы, требующие большого умственного напряжения.
    # «Каждый из них допускается изучать на первом или последнем учебном
    # занятии не чаще одного раза в неделю в одном классе» (V–XI).
    hard_subjects: list[str] = field(default_factory=list)
    hard_max_first_or_last: int | None = None
    hard_parallels: list[int] = field(default_factory=list)

    # --- п. 92 ССЭТ: в каких параллелях запрещена вторая смена.
    second_shift_forbidden_parallels: list[int] = field(default_factory=list)
    second_shift_forbidden_if_advanced: list[int] = field(default_factory=list)

    # --- п. 65 ССЭТ: сдвоенные уроки.
    # «Допускается объединять… по отдельным учебным предметам в виде сдвоенных
    # уроков, изучаемых на повышенном уровне в VIII–IX классах; по одному учебному
    # предмету в виде сдвоенных уроков в X–XI классах… по учебному предмету
    # «Трудовое обучение», кроме I–IV классов». Физкультуру объединять нельзя.
    double_advanced_parallels: list[int] = field(default_factory=list)
    double_always_allowed: list[str] = field(default_factory=list)
    double_min_parallel_for_labour: int | None = None
    double_forbidden_subjects: list[str] = field(default_factory=list)
    double_must_be_consecutive: bool = True

    # --- п. 67 ССЭТ + ИМП 2025: контрольные работы.
    tests_forbidden_last_period: bool = False
    tests_optimal_periods: list[int] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not (self.max_hours_per_week or self.max_lessons_per_day)

    def difficulty(self, subject_name: str, parallel: int) -> int | None:
        """Балл трудности предмета для параллели. None = нормы не покрывают."""
        by_parallel = self.difficulty_scale.get(subject_name)
        if not by_parallel:
            return None
        return by_parallel.get(parallel) or by_parallel.get(str(parallel))

    def hours_limit(self, parallel: int, advanced: bool = False) -> int | None:
        """Предельная недельная нагрузка с учётом повышенного уровня."""
        if advanced and parallel in self.max_hours_per_week_advanced:
            return self.max_hours_per_week_advanced[parallel]
        return self.max_hours_per_week.get(parallel)

    def peak_days(self, parallel: int) -> list[int]:
        """Дни наибольшей работоспособности для параллели."""
        return self.peak_days_1_4 if parallel <= 4 else self.peak_days_5_11

    def is_hard_subject(self, subject_name: str) -> bool:
        return subject_name in self.hard_subjects

    def double_allowed(self, subject_name: str, parallel: int, advanced: bool) -> bool:
        """Можно ли ставить два урока этого предмета в один день подряд.

        Разрешение из п. 65 ССЭТ. Нужно там, где часов больше, чем учебных дней:
        математика на повышенном уровне — 6 часов при пятидневке.
        """
        if self.is_pe(subject_name) or subject_name in self.double_forbidden_subjects:
            return False
        if subject_name in self.double_always_allowed:
            least = self.double_min_parallel_for_labour
            return least is None or parallel >= least
        return advanced and parallel in self.double_advanced_parallels

    def is_pe(self, subject_name: str) -> bool:
        """Физкультура ли это. Сравниваем по началу названия: в школьных
        данных предмет пишут и «Физическая культура и здоровье», и «Физкультура»."""
        if not self.pe_subject or not subject_name:
            return False
        a, b = subject_name.lower(), self.pe_subject.lower()
        return a.startswith(b[:12]) or a.startswith("физкульт") or a.startswith("физ-ра")


@dataclass
class School:
    """Полный вход задачи."""

    name: str
    classes: list[SchoolClass] = field(default_factory=list)
    groups: list[StudyGroup] = field(default_factory=list)
    teachers: list[Teacher] = field(default_factory=list)
    subjects: list[Subject] = field(default_factory=list)
    rooms: list[Room] = field(default_factory=list)
    load: list[LoadItem] = field(default_factory=list)
    bells: list[BellSchedule] = field(default_factory=list)
    norms: Norms = field(default_factory=Norms)
    # Какие дни какого типа. По умолчанию пн–пт уроки, суббота — шестой день.
    day_kinds: dict[int, DayKind] = field(
        default_factory=lambda: {d: DayKind.LESSONS for d in range(1, 6)} | {6: DayKind.SIXTH_DAY}
    )
    periods_per_day: int = 8

    def lesson_slots(self, shift: Shift = Shift.FIRST) -> list[Slot]:
        """Все слоты, куда физически можно поставить урок."""
        return [
            Slot(day, period, shift)
            for day, kind in sorted(self.day_kinds.items())
            if kind == DayKind.LESSONS
            for period in range(1, self.periods_per_day + 1)
        ]

    def group(self, group_id: str) -> StudyGroup:
        return next(g for g in self.groups if g.id == group_id)
