"""Солвер расписания на CP-SAT.

Как это работает (объяснение, а не магия):

  1. Заводим БУЛЕВУ ПЕРЕМЕННУЮ x[нагрузка, слот] — «этот урок стоит в этой клетке».
     Их много (нагрузка × слоты), но солвер не перебирает их тупо.
  2. Пишем HARD-ограничения — то, что запрещено абсолютно. Это не проверки
     постфактум, а условия, внутри которых солвер вообще ищет.
  3. Запускаем. CP-SAT сам решает, как искать.

Наша работа — правильно описать ограничения. Алгоритм поиска писать не надо.

Реализованы HARD 1, 2, 4, 6, 8, 9 и SOFT 1, 2, 3, 5 (см. CLAUDE.md §7.4).
Ограничения, зависящие от норм, не применяются, пока Norms пуст — вместо того,
чтобы применяться с выдуманной цифрой.

Про SOFT (объяснение). HARD говорит «так нельзя никогда». SOFT говорит
«так нежелательно, и вот сколько это стоит». Каждое нарушение SOFT прибавляет
очки штрафа, а солвер минимизирует их сумму — целевую функцию. Поэтому SOFT
не запрещает, а торгуется: одно окно у учителя допустимо, если иначе развалится
день у трёх классов. Веса штрафов задают, что нам дороже.
"""

from collections import defaultdict
import os
import time
from pathlib import Path
from dataclasses import dataclass, field

from ortools.sat.python import cp_model

from .model import Lesson, Level, School, Shift, Slot


@dataclass
class Weights:
    """Веса штрафов — «цена» каждого нарушения SOFT в очках.

    Важны не абсолютные значения, а их соотношение. Окно у учителя дороже
    лишнего дня присутствия, потому что окно — это час в школе без дела,
    а лишний день — это дорога.
    """

    teacher_gap: int = 10  # SOFT-1: окно у учителя
    teacher_day: int = 3  # SOFT-3: каждый день присутствия учителя в школе
    class_imbalance: int = 2  # SOFT-5: разброс нагрузки класса по дням (в уроках)
    difficulty_imbalance: int = 4  # п. 88.2 СанПиН: разброс по БАЛЛАМ трудности
    teacher_wish: int = 6  # пожелание учителя («нежелательно», а не «не могу»)
    peak_day: int = 3  # п. 94 ССЭТ: пик нагрузки не в день работоспособности
    pe_rule: int = 8  # п. 94 ССЭТ: физкультура, если правило переведено в мягкие
    hard_subject_edge: int = 5  # п. 94 ССЭТ: трудный предмет на краю дня


# Готовые наборы весов. Завучу не нужно знать слово «штраф»: ему нужно решить,
# чьё удобство важнее, когда всем сразу угодить нельзя. Числа — уже наше дело.
PRESETS = {
    "Поровну": {
        "weights": Weights(),
        "about": "Обычный компромисс: и учителям, и детям понемногу. "
                 "С этого стоит начать.",
    },
    "Учителям удобнее": {
        "weights": Weights(teacher_gap=16, teacher_day=7, class_imbalance=1,
                           difficulty_imbalance=2, teacher_wish=9),
        "about": "Меньше окон и лишних выходов в школу, пожелания соблюдаются чаще. "
                 "Расплата: дни у классов выйдут неровнее — где-то 5 уроков, где-то 8.",
    },
    "Детям легче": {
        "weights": Weights(teacher_gap=5, teacher_day=2, class_imbalance=6,
                           difficulty_imbalance=9, teacher_wish=3),
        "about": "Ровная нагрузка по дням и трудные предметы распределены по неделе. "
                 "Расплата: у учителей появятся окна и лишние выходы в школу.",
    },
}


@dataclass
class Rules:
    """Насколько строго применять каждую норму.

    Три состояния у каждой:
      "hard" — запрет. Солвер не поставит так никогда.
      "soft" — штраф. Поставит, если иначе расписание не сходится, но постарается не ставить.
      "off"  — не применять вовсе.

    Зачем переключатели. Норма — это требование к школе, а не к алгоритму.
    Если жёстко применить всё сразу на данных, где часов больше, чем места,
    солвер вернёт INFEASIBLE без объяснения — и завуч останется ни с чем.
    Переключатель даёт ему выбор: ослабить норму и увидеть расписание
    с пометкой о нарушении, а не упереться в стену (docs/domain.md §4.8).

    Значения по умолчанию — как в первоисточнике: «не допускается» → hard,
    «оптимально/рекомендуется» → soft.
    """

    pe_two_days: str = "hard"  # п. 94: физкультура не два дня подряд
    pe_edges: str = "hard"  # п. 94: физкультура первой/последней ≤ 1 раза в неделю
    hard_subject_edges: str = "hard"  # п. 94: трудный предмет на краю дня ≤ 1 раза
    peak_days: str = "soft"  # п. 94: максимум нагрузки во вторник/среду/пятницу
    difficulty_balance: str = "soft"  # п. 88.2: равномерность по трудности
    even_days: str = "soft"  # ровное число уроков по дням (не норма, а качество)
    teacher_wishes: str = "soft"  # пожелания учителей (не норма, а договорённость)

    def on(self, name: str) -> bool:
        return getattr(self, name, "off") != "off"

    def is_hard(self, name: str) -> bool:
        return getattr(self, name, "off") == "hard"


class SolveResult:
    def __init__(
        self, status: str, lessons: list[Lesson], wall_time: float, penalty: int | None = None,
        relaxed: list[str] | None = None,
    ):
        self.status = status
        self.lessons = lessons
        self.wall_time = wall_time
        self.penalty = penalty
        # Нормы, которые пришлось ослабить точечно — по одному классу, а не
        # по всей школе. Завуч обязан знать, где именно и почему: это те места,
        # за которые он отвечает перед проверкой (docs/domain.md §4.8).
        self.relaxed = relaxed or []

    @property
    def ok(self) -> bool:
        return self.status in ("OPTIMAL", "FEASIBLE")


@dataclass
class Progress:
    """Снимок хода поиска — то, что видит завуч, пока идёт составление.

    Солвер не умеет сказать «осталось три минуты»: он либо доказывает
    оптимальность и останавливается сам, либо работает до конца бюджета.
    Единственная честная мера продвижения — `gap`: насколько текущее решение
    ещё может улучшиться в принципе. Когда он падает до нуля, поиск закончен.
    """

    stage: str  # "search" — ищем законное расписание, "improve" — улучшаем
    seconds: float
    budget: float
    solutions: int
    penalty: int | None = None
    bound: int | None = None
    metrics: dict[str, int] = field(default_factory=dict)

    @property
    def gap(self) -> float | None:
        """Доля возможного улучшения, 0..1. None, пока не с чем сравнивать."""
        if self.penalty is None or self.bound is None or self.penalty <= 0:
            return None
        return max(0.0, min(1.0, (self.penalty - self.bound) / self.penalty))


class _Reporter(cp_model.CpSolverSolutionCallback):
    """Докладывает наверх при каждом улучшении и слушает просьбу остановиться.

    Значения метрик читаются прямо из переменных модели — поэтому в интерфейсе
    видно «окон у учителей 456 → 120», а не абстрактную сумму штрафов, которая
    завучу ничего не говорит.
    """

    def __init__(self, trackers: dict[str, list], budget: float,
                 on_progress, should_stop, started_at: float):
        super().__init__()
        self._trackers = trackers
        self._budget = budget
        self._on_progress = on_progress
        self._should_stop = should_stop
        self._started = started_at
        self.solutions = 0

    def on_solution_callback(self) -> None:
        self.solutions += 1
        metrics = {}
        for label, variables in self._trackers.items():
            try:
                metrics[label] = sum(int(self.Value(v)) for v in variables)
            except Exception:
                continue
        if self._on_progress:
            self._on_progress(Progress(
                stage="improve",
                seconds=time.monotonic() - self._started,
                budget=self._budget,
                solutions=self.solutions,
                penalty=int(self.ObjectiveValue()) if self._trackers else None,
                bound=int(self.BestObjectiveBound()) if self._trackers else None,
                metrics=metrics,
            ))
        if self._should_stop and self._should_stop():
            self.StopSearch()


def available_cpus() -> int:
    """Сколько процессорных ядер реально досталось процессу.

    `os.cpu_count()` отвечает на другой вопрос — сколько ядер у ЖЕЛЕЗА. В
    контейнере это ядра хоста, а не выделенная квота, и разница огромная:
    на бесплатном Streamlit Cloud процесс видит восемь ядер, а получает
    доли одного.

    ⚠️ Ограничивать число потоков этой цифрой НЕЛЬЗЯ, и это неочевидно.
    Замерено 26.08.2026 на районной школе (14 классов), поиск первого решения:

        1 поток  → не нашёл за 120 с      = 120 процессорных секунд впустую
        2 потока → нашёл за 12,8 с        =  26 процессорных секунд
        4 потока → нашёл за 3,8 с         =  15 процессорных секунд

    CP-SAT держит в потоках РАЗНЫЕ стратегии поиска и берёт ту, что сработала
    первой. Одному потоку достаётся одна стратегия, и он может не найти ничего.
    Поэтому лишние потоки на слабой машине не разоряют, а ЭКОНОМЯТ процессорное
    время: решение находится настолько раньше, что суммарный расход падает.
    Отсюда `max(4, ...)` в вызове: четыре стратегии минимум, сколько бы ядер
    ни было.

    Тогда зачем считать квоту вообще — чтобы не заводить шестнадцать потоков
    там, где их обслуживать нечем: сверх нескольких штук выигрыш от новых
    стратегий сходит на нет, а переключение контекста остаётся.

    Порядок проверок — от самого точного к самому грубому:
      1. cgroup v2 (`cpu.max`) и v1 (`cpu.cfs_quota_us`) — квота контейнера,
         единственный источник, знающий про ограничение;
      2. `sched_getaffinity` — маска ядер, на которых процессу разрешено идти;
      3. `os.cpu_count()` — ядра железа, последняя надежда.
    """
    limits = []

    # --- квота cgroup: «сколько микросекунд CPU за период» → доля ядра
    try:  # cgroup v2: строка вида "200000 100000" либо "max 100000"
        quota, period = Path("/sys/fs/cgroup/cpu.max").read_text().split()
        if quota != "max":
            limits.append(int(quota) / int(period))
    except (OSError, ValueError):
        pass
    try:  # cgroup v1: квота и период лежат в разных файлах
        quota = int(Path("/sys/fs/cgroup/cpu/cpu.cfs_quota_us").read_text())
        period = int(Path("/sys/fs/cgroup/cpu/cpu.cfs_period_us").read_text())
        if quota > 0 and period > 0:
            limits.append(quota / period)
    except (OSError, ValueError):
        pass

    if hasattr(os, "sched_getaffinity"):  # на macOS его нет
        limits.append(len(os.sched_getaffinity(0)))
    limits.append(os.cpu_count() or 1)

    # Дробную квоту округляем ВНИЗ: пол-ядра — это один поток, а не два.
    # И не меньше одного, иначе солверу нечем работать.
    return max(1, int(min(limits)))


def solve(
    school: School,
    shift: Shift = Shift.FIRST,
    max_seconds: float = 120.0,
    weights: Weights | None = None,
    optimize: bool = True,
    rules: Rules | None = None,
    on_progress=None,
    should_stop=None,
    pinned: list[Lesson] | None = None,
    params: dict | None = None,
    hierarchical: bool = False,
    ignore_rooms: bool = False,
) -> SolveResult:
    """Составить расписание.

    `on_progress` вызывается при каждом улучшении решения со снимком `Progress`,
    `should_stop` спрашивается там же — если вернёт True, поиск прекращается
    и возвращается лучшее найденное. Оба нужны интерфейсу: составление идёт
    минутами, и завуч должен видеть, что происходит, и мочь прервать.

    `pinned` — уроки, которые обязаны остаться на своих местах. Первый вопрос
    завуча к готовому расписанию всегда один: «вот здесь надо подвинуть».
    Пересобирать всё заново нельзя — вместе с неудобным уроком переедет
    и то, что его устраивало. Поэтому лишнее закрепляется, а пересобирается
    только спорная часть.
    """
    model = cp_model.CpModel()
    rules = rules or Rules()
    slots = school.lesson_slots(shift)
    started_at = time.monotonic()

    # Переменные, по которым считаются ЖИВЫЕ метрики для интерфейса.
    # Те же величины, что потом покажет валидатор, — но их видно уже в процессе.
    trackers: dict[str, list] = defaultdict(list)

    # --- переменные: x[i, slot] = 1, если i-я строка нагрузки стоит в этом слоте
    x: dict[tuple[int, Slot], cp_model.IntVar] = {}
    for i, item in enumerate(school.load):
        for slot in slots:
            x[i, slot] = model.NewBoolVar(f"x_{i}_{slot}")

    x_slots = set(slots)

    # --- HARD-4: все часы из нагрузки выданы ровно в нужном количестве
    for i, item in enumerate(school.load):
        model.Add(sum(x[i, s] for s in slots) == item.hours_per_week)

    # --- закреплённые уроки: стоят там, где стояли, и не обсуждаются.
    # Строка нагрузки даёт несколько уроков в неделю, и они взаимозаменяемы,
    # поэтому достаточно потребовать «эта строка занимает этот слот».
    if pinned:
        by_key: dict[tuple[str, str, str], list[int]] = defaultdict(list)
        for i, item in enumerate(school.load):
            by_key[item.group_id, item.subject_id, item.teacher_id].append(i)
        for lesson in pinned:
            indices = by_key.get(
                (lesson.group_id, lesson.subject_id, lesson.teacher_id))
            if not indices:
                continue
            slot = lesson.slot if lesson.slot in x_slots else None
            if slot is not None:
                model.Add(x[indices[0], slot] == 1)

    # --- HARD-4b: один и тот же предмет не стоит у группы дважды в один день
    # (иначе солвер честно поставит 5 математик подряд в понедельник).
    #
    # Исключение — СДВОЕННЫЕ УРОКИ, п. 65 ССЭТ № 525: они допускаются по предметам
    # на повышенном уровне в VIII–XI и по трудовому обучению. Без этого исключения
    # профильный класс не составляется в принципе: математика на повышенном уровне
    # даёт 6 часов, а пятидневка при «не дважды в день» вмещает максимум 5.
    # Найдено на данных школы 24.08.2026.
    #
    # Если два урока в день — они идут ПОДРЯД. Иначе это не сдвоенный урок,
    # а два отдельных, что нормой не разрешено.
    class_parallels = {c.id: c.parallel for c in school.classes}
    names_of_subject = {s.id: s.name for s in school.subjects}
    for i, item in enumerate(school.load):
        group = school.group(item.group_id)
        parallel = max((class_parallels.get(c, 0) for c in group.class_ids), default=0)
        subject_name = names_of_subject.get(item.subject_id, "")
        двойной = school.norms.double_allowed(
            subject_name, parallel, item.level != Level.BASE)

        by_day: dict[int, list] = defaultdict(list)
        for slot in slots:
            by_day[slot.day].append(x[i, slot])
        for day, day_vars in by_day.items():
            model.Add(sum(day_vars) <= (2 if двойной else 1))
            if двойной and school.norms.double_must_be_consecutive:
                for p1 in range(1, school.periods_per_day + 1):
                    for p2 in range(p1 + 2, school.periods_per_day + 1):
                        model.Add(x[i, Slot(day, p1, shift)] + x[i, Slot(day, p2, shift)] <= 1)

    # --- HARD-1: учитель не ведёт два урока одновременно
    by_teacher: dict[str, list[int]] = defaultdict(list)
    for i, item in enumerate(school.load):
        by_teacher[item.teacher_id].append(i)
    for indices in by_teacher.values():
        for slot in slots:
            model.Add(sum(x[i, slot] for i in indices) <= 1)

    # --- HARD-2: класс не имеет двух уроков одновременно.
    # Считаем ПО КЛАССАМ, а не по группам: две подгруппы одного класса
    # могут идти параллельно (деление), но полный класс с подгруппой — нет.
    # Полный класс занимает класс целиком (вес 1), подгруппа — тоже 1,
    # поэтому ограничение пишем отдельно для целых классов и для каждой части.
    whole: dict[str, list[int]] = defaultdict(list)  # класс → строки нагрузки целого класса
    parts: dict[tuple[str, str], list[int]] = defaultdict(list)  # (класс, часть) → строки
    for i, item in enumerate(school.load):
        group = school.group(item.group_id)
        for class_id in group.class_ids:
            if group.is_whole_class:
                whole[class_id].append(i)
            else:
                parts[class_id, group.part or ""].append(i)

    # Сколько СЛОТОВ в неделе занимает класс. Не то же самое, что сумма строк
    # нагрузки: две подгруппы иностранного идут одновременно и стоят классу
    # одного слота, а не двух. Нужно для коридора уроков в дне (ниже).
    class_week_hours: dict[str, int] = {}
    for class_id in whole:
        hours = sum(school.load[i].hours_per_week for i in whole[class_id])
        by_subject: dict[str, int] = {}
        for (cid, _), indices in parts.items():
            if cid != class_id:
                continue
            for i in indices:
                item = school.load[i]
                # у деления часы одинаковы у обеих подгрупп — берём наибольший
                by_subject[item.subject_id] = max(
                    by_subject.get(item.subject_id, 0), item.hours_per_week)
        class_week_hours[class_id] = hours + sum(by_subject.values())

    for class_id, whole_indices in whole.items():
        part_groups = [v for (cid, _), v in parts.items() if cid == class_id]
        for slot in slots:
            # целый класс — максимум один урок в слот
            model.Add(sum(x[i, slot] for i in whole_indices) <= 1)
            # каждая подгруппа — максимум один урок в слот
            for part_indices in part_groups:
                model.Add(sum(x[i, slot] for i in part_indices) <= 1)
            # целый класс и любая подгруппа не могут пересечься
            for part_indices in part_groups:
                model.Add(
                    sum(x[i, slot] for i in whole_indices)
                    + sum(x[i, slot] for i in part_indices)
                    <= 1
                )

    # --- HARD-9: подгруппы одного деления идут СИНХРОННО, в один слот.
    # Мало разрешить двум подгруппам стоять в одном слоте (это делает HARD-2) —
    # надо потребовать, чтобы они там стояли. Иначе солвер разведёт гр.1 и гр.2
    # по разным дням, и полкласса будет ждать, пока вторая половина учится.
    # Деление = один класс + один предмет + несколько частей.
    splits: dict[tuple[str, str], list[int]] = defaultdict(list)
    for i, item in enumerate(school.load):
        group = school.group(item.group_id)
        if group.part is not None and len(group.class_ids) == 1:
            splits[group.class_ids[0], item.subject_id].append(i)

    for (class_id, subject_id), indices in splits.items():
        if len(indices) < 2:
            continue
        hours = {school.load[i].hours_per_week for i in indices}
        if len(hours) > 1:
            # У подгрупп разное число часов — синхронизировать нечем.
            # Это не наш баг, а особенность данных школы: сообщаем и пропускаем.
            print(
                f"  ⚠️  {class_id}/{subject_id}: у подгрупп разное число часов {sorted(hours)}"
                " — синхронность не наложена"
            )
            continue
        first, *rest = indices
        for other in rest:
            for slot in slots:
                model.Add(x[first, slot] == x[other, slot])

    # --- HARD-8: у класса нет окон — класс учится подряд с первого урока.
    # Заводим отдельную переменную busy[класс, слот] = «класс чем-то занят».
    # Она нужна потому, что при делении в одном слоте стоят ДВА урока, а занятость
    # всё равно одна. Дальше требуем, чтобы занятость по дню шла без разрывов:
    # если занят урок p+1, то занят и урок p. Это и есть «нет окон».
    busy: dict[tuple[str, Slot], cp_model.IntVar] = {}
    for class_id in whole:
        class_indices = whole[class_id] + [
            i for (cid, _), v in parts.items() if cid == class_id for i in v
        ]
        for slot in slots:
            var = model.NewBoolVar(f"busy_{class_id}_{slot}")
            model.AddMaxEquality(var, [x[i, slot] for i in class_indices])
            busy[class_id, slot] = var

        for day in {s.day for s in slots}:
            for period in range(1, school.periods_per_day):
                model.Add(
                    busy[class_id, Slot(day, period, shift)]
                    >= busy[class_id, Slot(day, period + 1, shift)]
                )

    # --- HARD-3 и HARD-5: кабинеты.
    # Не назначаем каждому уроку конкретный кабинет — это раздуло бы модель
    # в десятки раз (нагрузка × слоты × кабинеты). Вместо этого ограничиваем
    # ЁМКОСТЬ: в один слот не может идти больше уроков химии, чем есть кабинетов
    # химии. Спортзалов два — значит два урока физкультуры одновременно можно,
    # три нельзя. Конкретный кабинет назначается уже после решения (assign_rooms):
    # если ёмкость соблюдена, назначение всегда существует.
    #
    # Обычные кабинеты считаем так же — это заодно ловит ситуацию «уроков больше,
    # чем классных комнат в школе».
    rooms_by_kind: dict = defaultdict(list)
    for room in school.rooms:
        rooms_by_kind[room.kind].append(room)

    subject_room = {s.id: s.required_room for s in school.subjects}
    load_by_kind: dict = defaultdict(list)
    for i, item in enumerate(school.load):
        if item.room_id:
            continue  # кабинет закреплён жёстко — обрабатываем ниже
        kind = item.room_kind or subject_room.get(item.subject_id)
        if kind is not None:
            load_by_kind[kind].append(i)

    for kind, indices in load_by_kind.items() if not ignore_rooms else []:
        capacity = len(rooms_by_kind.get(kind, []))
        if capacity == 0:
            # Предмет требует кабинета, которого в школе нет. Не молчим:
            # это ошибка данных, а не невыполнимая задача.
            print(f"  ⚠️  нет ни одного кабинета типа {kind.value} — ограничение не наложено")
            continue
        for slot in slots:
            model.Add(sum(x[i, slot] for i in indices) <= capacity)

    # Жёстко закреплённый кабинет: занят одним уроком за раз (HARD-3).
    fixed_rooms: dict[str, list[int]] = defaultdict(list)
    for i, item in enumerate(school.load):
        if item.room_id:
            fixed_rooms[item.room_id].append(i)
    if not ignore_rooms:
        for indices in fixed_rooms.values():
            for slot in slots:
                model.Add(sum(x[i, slot] for i in indices) <= 1)

    # --- HARD-6: учитель не ставится в свои недоступные слоты
    teacher_by_id = {t.id: t for t in school.teachers}
    for i, item in enumerate(school.load):
        teacher = teacher_by_id[item.teacher_id]
        for slot in slots:
            if slot in teacher.unavailable or slot.day == teacher.method_day:
                model.Add(x[i, slot] == 0)

    # ================== SOFT: то, что штрафуется, а не запрещается ==================
    w = weights or Weights()
    days = sorted({s.day for s in slots})
    penalties = []  # (переменная, вес)
    relaxed: list[str] = []  # нормы, ослабленные точечно — по классу, а не по школе

    # --- SOFT-1 и SOFT-3: окна у учителей и число дней присутствия.
    # Окно считаем так: у учителя в дне есть первый урок и последний. Между ними
    # он в школе. Окна = (последний − первый + 1) − сколько уроков реально стоит.
    # Учитель с уроками на 1-м и 7-м — в школе 7 часов ради двух: 5 окон.
    # Приём: «учитель в школе на уроке p» = он УЖЕ начал (был урок в ≤ p)
    # И ещё НЕ закончил (будет урок в ≥ p). Обе половины — монотонные флаги,
    # их солвер считает почти бесплатно:
    #   started[p] — был ли урок в периоды 1..p   (не убывает слева направо)
    #   rest[p]    — будет ли урок в периоды p..P (не убывает справа налево)
    # Тогда окна = (часов в школе) − (уроков).
    #
    # ⚠️ Наивная версия «если занят сосед слева и справа, то занят и здесь»
    # НЕ РАБОТАЕТ: она затыкает дыру в один урок, но пропускает дыру в два подряд.
    # Проверено 22.08.2026 — солвер считал окна нулём, метрика видела 14.
    for teacher_id, indices in by_teacher.items():
        for day in days:
            periods = list(range(1, school.periods_per_day + 1))
            t_busy, started, rest, present = {}, {}, {}, {}
            for period in periods:
                slot = Slot(day, period, shift)
                busy_var = model.NewBoolVar(f"tb_{teacher_id}_{slot}")
                model.AddMaxEquality(busy_var, [x[i, slot] for i in indices])
                t_busy[period] = busy_var
                started[period] = model.NewBoolVar(f"st_{teacher_id}_{slot}")
                rest[period] = model.NewBoolVar(f"rs_{teacher_id}_{slot}")
                present[period] = model.NewBoolVar(f"pres_{teacher_id}_{slot}")

            for period in periods:
                model.Add(started[period] >= t_busy[period])
                model.Add(rest[period] >= t_busy[period])
                if period > 1:
                    model.Add(started[period] >= started[period - 1])
                if period < school.periods_per_day:
                    model.Add(rest[period] >= rest[period + 1])
                # в школе = начал и ещё не закончил
                model.Add(present[period] >= started[period] + rest[period] - 1)

            works = model.NewBoolVar(f"works_{teacher_id}_{day}")
            for period in periods:
                model.Add(works >= t_busy[period])

            gaps = model.NewIntVar(0, school.periods_per_day, f"gaps_{teacher_id}_{day}")
            model.Add(gaps == sum(present.values()) - sum(t_busy.values()))

            penalties.append((gaps, w.teacher_gap))
            penalties.append((works, w.teacher_day))  # SOFT-3: меньше дней в школе
            trackers["Окна у учителей"].append(gaps)
            trackers["Выходы в школу"].append(works)

    # --- SOFT-5 + коридор дня: равномерная нагрузка класса по дням.
    #
    # Одного штрафа за разброс мало. На большой школе солвер экономит его
    # в последнюю очередь и спокойно оставляет день с двумя уроками рядом
    # с днём на восемь: формально дёшево, а для ребёнка это выброшенный день
    # (приехал ради двух уроков) и переполненный следующий.
    #
    # Поэтому число уроков в дне зажимается в коридор, посчитанный из недельной
    # нагрузки самого класса: [нагрузка // дней, ceil(нагрузка / дней)].
    # Для 28 часов на пятидневке это ровно 5–6 уроков, для 35 часов — 7.
    # Коридор всегда достижим по арифметике (сумма нижних границ ≤ нагрузка
    # ≤ сумма верхних), поэтому нерешаемым он делает задачу только вместе
    # с другими ограничениями — и тогда его переключают в «мягко».
    day_count = len(days)
    for class_id in whole:
        per_day = []
        for day in days:
            count = model.NewIntVar(0, school.periods_per_day, f"cnt_{class_id}_{day}")
            model.Add(count == sum(busy[class_id, s] for s in slots if s.day == day))
            per_day.append(count)

        total = class_week_hours.get(class_id, 0)
        low = total // day_count if day_count else 0
        high = -(-total // day_count) if day_count else 0
        high = min(high, school.periods_per_day)

        if total and rules.on("even_days") and low <= high:
            # Жёсткая граница шире идеала на урок в каждую сторону, а к идеалу
            # тянет штраф. Идеальный коридор «ровно 5–6» оказался неподъёмным:
            # на 28 классах поиск ЛЮБОГО расписания стал нестабильным — то 10
            # секунд, то не находит за 45 вовсе (замерено 25.08.2026, три прогона
            # из трёх разошлись). Допуск в один урок возвращает солверу свободу,
            # а штраф всё равно приводит дни к 5–6: разброс по школе остаётся
            # тем же, но результат появляется всегда.
            hard_low = max(1, low - 1)
            hard_high = min(school.periods_per_day, high + 1)
            for count in per_day:
                if rules.is_hard("even_days"):
                    # «Жёстко» — идеальный коридор без допуска: дни выходят
                    # ровно 5–6 при 28 часах. Ровнее не бывает, но модель
                    # становится тяжёлой и расписание может не найтись вовсе.
                    model.Add(count >= low)
                    model.Add(count <= high)
                elif rules.on("even_days"):
                    model.Add(count >= hard_low)
                    model.Add(count <= hard_high)
                short = model.NewIntVar(0, school.periods_per_day, f"short_{count.Name()}")
                over = model.NewIntVar(0, school.periods_per_day, f"over_{count.Name()}")
                model.Add(short >= low - count)
                model.Add(over >= count - high)
                # Вес больше обычного разброса: отклонение от идеального
                # коридора — это ровно тот день из четырёх уроков, ради
                # которого коридор и вводился.
                penalties.append((short, w.class_imbalance * 8))
                penalties.append((over, w.class_imbalance * 8))

        day_max = model.NewIntVar(0, school.periods_per_day, f"max_{class_id}")
        day_min = model.NewIntVar(0, school.periods_per_day, f"min_{class_id}")
        model.AddMaxEquality(day_max, per_day)
        model.AddMinEquality(day_min, per_day)

        spread = model.NewIntVar(0, school.periods_per_day, f"spread_{class_id}")
        model.Add(spread == day_max - day_min)
        penalties.append((spread, w.class_imbalance))
        trackers["Разброс дней"].append(spread)

    parallels = {c.id: c.parallel for c in school.classes}
    subject_names = {s.id: s.name for s in school.subjects}

    # --- Пожелания учителей: «нежелательно», а не «не могу».
    # Отличие от HARD-6 принципиальное. Если все пожелания сделать запретами,
    # расписание перестанет существовать: у каждого учителя найдётся своё «только
    # не в пятницу». Штраф позволяет солверу нарушить пожелание, когда иначе никак,
    # и при этом нарушить как можно меньше их.
    if rules.on("teacher_wishes"):
        for i, item in enumerate(school.load):
            teacher = teacher_by_id[item.teacher_id]
            for slot in teacher.disliked:
                if (i, slot) in x:
                    penalties.append((x[i, slot], w.teacher_wish))

    # --- Вспомогательное: «этот урок — последний в дне у класса».
    # Нужно для норм про первый/последний урок. Первый урок — всегда № 1:
    # HARD-8 гарантирует, что класс учится подряд с начала дня, без окон.
    # А последний — плавающий: в один день их шесть, в другой восемь.
    # last[класс, день, урок] = класс занят здесь И не занят на следующем уроке.
    last: dict[tuple[str, int, int], cp_model.IntVar] = {}
    need_edges = (rules.on("pe_edges") and school.norms.pe_max_first_or_last is not None) or (
        rules.on("hard_subject_edges") and school.norms.hard_subjects
    )
    if need_edges:
        for class_id in whole:
            for day in days:
                for period in range(1, school.periods_per_day + 1):
                    var = model.NewBoolVar(f"last_{class_id}_{day}_{period}")
                    here = busy[class_id, Slot(day, period, shift)]
                    if period == school.periods_per_day:
                        model.Add(var == here)
                    else:
                        nxt = busy[class_id, Slot(day, period + 1, shift)]
                        # var = here AND NOT nxt
                        model.Add(var <= here)
                        model.Add(var + nxt <= 1)
                        model.Add(var >= here - nxt)
                    last[class_id, day, period] = var

    def edge_count(indices: list[int], class_id: str, tag: str):
        """Сколько раз за неделю эти уроки стоят первыми или последними в дне."""
        terms = []
        for day in days:
            for i in indices:
                terms.append(x[i, Slot(day, 1, shift)])  # первый урок — всегда № 1
                for period in range(1, school.periods_per_day + 1):
                    if period == 1:
                        continue  # уже посчитан как первый
                    both = model.NewBoolVar(f"edge_{tag}_{i}_{day}_{period}")
                    model.Add(both <= x[i, Slot(day, period, shift)])
                    model.Add(both <= last[class_id, day, period])
                    model.Add(both >= x[i, Slot(day, period, shift)]
                              + last[class_id, day, period] - 1)
                    terms.append(both)
        return terms

    def limit(mode: str, terms: list, cap: int, weight: int, tag: str):
        """Применить ограничение «не больше cap» жёстко или через штраф."""
        if not terms:
            return
        if mode == "hard":
            model.Add(sum(terms) <= cap)
        else:  # soft: нарушение = превышение над cap, штрафуется
            over = model.NewIntVar(0, len(terms), f"over_{tag}")
            model.Add(over >= sum(terms) - cap)
            penalties.append((over, weight))
            trackers["Нарушений норм"].append(over)

    # --- п. 94 ССЭТ № 525: физическая культура.
    # «Не допускается проведение учебных занятий по учебному предмету
    # «Физическая культура и здоровье» в течение двух дней подряд в одном классе
    # и более одного раза в неделю первыми или последними учебными занятиями».
    #
    # Смысл нормы: мышечная нагрузка должна быть распределена по неделе, а не
    # слипаться в два дня. И физкультура последним уроком означает, что ребёнок
    # уходит домой разгорячённым, а первым — что приходит на урок неразмятым.
    norms = school.norms
    pe_indices: dict[str, list[int]] = defaultdict(list)
    hard_indices: dict[tuple[str, str], list[int]] = defaultdict(list)
    for i, item in enumerate(school.load):
        group = school.group(item.group_id)
        name = subject_names.get(item.subject_id, "")
        for class_id in group.class_ids:
            if norms.is_pe(name):
                pe_indices[class_id].append(i)
            elif norms.is_hard_subject(name) and parallels.get(class_id, 0) in norms.hard_parallels:
                hard_indices[class_id, item.subject_id].append(i)

    if rules.on("pe_two_days") and norms.pe_no_two_days_in_row:
        # Норма применяется ПО КЛАССАМ, а не одним переключателем на всю школу.
        # Причина из реальных данных: физкультура не может стоять два дня подряд,
        # значит при пятидневке в неделю помещается максимум три занятия
        # (пн-ср-пт). Класс, где физкультуры четыре часа, эту норму выполнить
        # не может физически. Раньше из-за одного такого класса завуч был обязан
        # ослабить норму целиком — и её начинали нарушать все 28 классов, которым
        # она была вполне по силам. Теперь послабление получает только тот класс,
        # которому норма не по силам, а остальным она остаётся запретом.
        room_for_pe = (len(days) + 1) // 2  # сколько занятий влезает без соседних дней
        for class_id, indices in pe_indices.items():
            pe_day = {}
            for day in days:
                var = model.NewBoolVar(f"pe_{class_id}_{day}")
                model.AddMaxEquality(var, [x[i, s] for i in indices for s in slots if s.day == day])
                pe_day[day] = var
            hours = sum(school.load[i].hours_per_week for i in indices)
            mode = rules.pe_two_days
            if mode == "hard" and hours > room_for_pe:
                mode = "soft"
                relaxed.append(
                    f"{class_id}: физкультуры {hours} ч в неделю, а без двух дней подряд "
                    f"их помещается {room_for_pe} (п. 94 ССЭТ № 525). Для этого класса "
                    f"норма посчитана мягко — в расписании она будет нарушена. "
                    f"Обычный выход: лишний час перенести в шестой школьный день."
                )
            for day, nxt in zip(days, days[1:]):
                if nxt == day + 1:  # именно соседние дни недели
                    limit(mode, [pe_day[day], pe_day[nxt]], 1, w.pe_rule,
                          f"pe2_{class_id}_{day}")

    if rules.on("pe_edges") and norms.pe_max_first_or_last is not None:
        for class_id, indices in pe_indices.items():
            limit(rules.pe_edges, edge_count(indices, class_id, f"pe_{class_id}"),
                  norms.pe_max_first_or_last, w.pe_rule, f"peedge_{class_id}")

    # --- п. 94 ССЭТ № 525: предметы, требующие большого умственного напряжения.
    # «В V–XI классах каждый из учебных предметов, требующих большого умственного
    # напряжения, сосредоточенности и внимания (математика, русский, белорусский,
    # иностранный языки, физика, химия), допускается изучать на первом или последнем
    # учебном занятии не чаще одного раза в неделю в одном классе».
    #
    # Обрати внимание: норма про КАЖДЫЙ предмет отдельно, а не про их сумму.
    # Математика на краю дня один раз и физика один раз — это законно.
    if rules.on("hard_subject_edges") and norms.hard_max_first_or_last is not None:
        for (class_id, subject_id), indices in hard_indices.items():
            limit(rules.hard_subject_edges, edge_count(indices, class_id, f"hs_{class_id}_{subject_id}"),
                  norms.hard_max_first_or_last, w.hard_subject_edge, f"hsedge_{class_id}_{subject_id}")

    # --- п. 88.2 СанПиН № 206 + п. 94 ССЭТ № 525: распределение трудности по дням.
    #
    # Два документа говорят об одном, но с разных сторон:
    #   • СанПиН п. 88.2 — «нагрузка должна равномерно распределяться по дням
    #     недели с учётом ранговой шкалы трудности учебных предметов»;
    #   • ССЭТ п. 94 — «максимальная учебная нагрузка должна быть в дни наибольшей
    #     работоспособности: вторник, среда и (или) пятница в V–XI классах,
    #     равномерно распределяться по другим дням учебной недели».
    #
    # Вместе это НЕ «ровно по всем дням». Это «пик — во вторник, среду или пятницу,
    # а остальные дни ровные между собой». Понедельник тяжёлым быть не должен:
    # работоспособность после выходных ещё низкая.
    #
    # Балл дня = сумма рангов трудности всех уроков этого дня. День с математикой,
    # физикой и химией тяжелее дня с физкультурой и трудом, даже если уроков поровну.
    if norms.difficulty_scale and rules.on("difficulty_balance"):
        max_day_score = school.periods_per_day * 12  # 12 — максимальный балл в шкале
        for class_id in whole:
            parallel = parallels.get(class_id)
            scored = []  # (индекс нагрузки, балл)
            for i in whole[class_id] + [
                idx for (cid, _), v in parts.items() if cid == class_id for idx in v
            ]:
                name = subject_names.get(school.load[i].subject_id, "")
                score = norms.difficulty(name, parallel)
                if score:
                    scored.append((i, score))
            if not scored:
                continue

            score_of_day = {}
            for day in days:
                total = model.NewIntVar(0, max_day_score, f"diff_{class_id}_{day}")
                model.Add(total == sum(
                    x[i, s] * score for i, score in scored for s in slots if s.day == day
                ))
                score_of_day[day] = total

            peak = [d for d in norms.peak_days(parallel or 5) if d in days] or []
            others = [d for d in days if d not in peak]

            # Равномерность — среди дней, которые не объявлены пиковыми.
            flat = [score_of_day[d] for d in (others or days)]
            if len(flat) > 1:
                hi = model.NewIntVar(0, max_day_score, f"dmax_{class_id}")
                lo = model.NewIntVar(0, max_day_score, f"dmin_{class_id}")
                model.AddMaxEquality(hi, flat)
                model.AddMinEquality(lo, flat)
                gap = model.NewIntVar(0, max_day_score, f"dspread_{class_id}")
                model.Add(gap == hi - lo)
                penalties.append((gap, w.difficulty_imbalance))
                trackers["Разброс трудности"].append(gap)

            # Пик — в дни наибольшей работоспособности: непиковый день не должен
            # быть тяжелее самого лёгкого пикового.
            if peak and others and rules.on("peak_days"):
                peak_lo = model.NewIntVar(0, max_day_score, f"peaklo_{class_id}")
                model.AddMinEquality(peak_lo, [score_of_day[d] for d in peak])
                for day in others:
                    excess = model.NewIntVar(0, max_day_score, f"excess_{class_id}_{day}")
                    model.Add(excess >= score_of_day[day] - peak_lo)
                    penalties.append((excess, w.peak_day))

    solver = cp_model.CpSolver()
    # Не меньше четырёх потоков, даже если ядер меньше, — см. available_cpus().
    solver.parameters.num_workers = max(4, min(16, available_cpus()))
    # Активнее использовать линейную релаксацию. Половина нашей модели — суммы
    # («не больше стольких часов в дне», «столько-то окон»), и приближённое
    # решение в дробях служит солверу ориентиром, отсекая безнадёжные ветки.
    # Замерено 25.08.2026 на 28 классах, три минуты на конфигурацию:
    #   как было              — штраф 7467, окон у учителей 236
    #   linearization_level=2 — штраф 6947, окон у учителей 143   ← взято
    #   symmetry_level=4      — штраф 7321 (классы различаются учителями,
    #                           переставлять их местами нечего)
    #   probing_level=2       — штраф 7985 (хуже: анализ вместо поиска)
    #   interleave+lns        — решения не нашёл вовсе
    solver.parameters.linearization_level = 2
    # …но только для ОПТИМИЗАЦИИ. Поиску первого расписания линейная релаксация
    # не помогает, а мешает: замерено 25.08.2026 — с ней первая фаза заняла
    # 48 секунд вместо четырёх. Перед ней уровень снижается, после — возвращается.
    # Точка для настройки поиска. Значения подбираются замерами, а не на глаз:
    # на каждой модели они работают по-разному, и «умные» параметры вполне
    # могут сделать хуже.
    for name, value in (params or {}).items():
        setattr(solver.parameters, name, value)
    fallback: list[Lesson] = []

    if optimize and penalties:
        # ДВЕ ФАЗЫ. Замерено 24.08.2026 на школе из 28 классов и 980 часов:
        # без целевой функции допустимое расписание находится за 13 секунд,
        # а с ней солвер за 10 минут не находит НИ ОДНОГО решения (UNKNOWN)
        # и возвращать нечего. Причина обычная для CP-SAT: с целевой функцией
        # поиск идёт другой стратегией и на большой модели не успевает даже
        # до первого допустимого решения.
        #
        # Поэтому сперва ищем любое законное расписание, отдаём его солверу
        # подсказкой (AddHint) и только потом просим улучшать. Так на выходе
        # ВСЕГДА есть расписание: хуже по метрикам, если времени не хватило,
        # но валидное. Для завуча это разница между «вот, правьте руками»
        # и «система ничего не выдала».
        # Первой фазе отдаём ВЕСЬ бюджет как потолок, а не четверть: модель без
        # целевой функции возвращается сразу, как только находит решение,
        # поэтому лишнего времени она не съест. Фиксированные 10 секунд чуть
        # не стоили работоспособности: коридор ровных дней сделал поиск дольше
        # (9 с вместо 2), и на 30-секундном бюджете система снова начала
        # отвечать «решения нет» — при том что решение находится.
        warmup = max_seconds
        if on_progress:
            on_progress(Progress(stage="search", seconds=0.0, budget=max_seconds,
                                 solutions=0))
        solver.parameters.max_time_in_seconds = warmup
        # Останавливаемся на ПЕРВОМ найденном расписании. Без этого солвер
        # продолжает работу и на 45-секундном бюджете то укладывался за 9 секунд,
        # то не возвращал ничего вовсе — а нам на этом шаге нужно только одно:
        # любое законное расписание, чтобы было что улучшать и что отдать.
        solver.parameters.stop_after_first_solution = True
        solver.parameters.linearization_level = 0
        first = solver.Solve(model)
        solver.parameters.stop_after_first_solution = False
        solver.parameters.linearization_level = 2
        spent = solver.WallTime()
        if first in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            for key, var in x.items():
                model.AddHint(var, solver.Value(var))
            if on_progress:
                on_progress(Progress(
                    stage="improve", seconds=time.monotonic() - started_at,
                    budget=max_seconds, solutions=1,
                    metrics={label: sum(int(solver.Value(v)) for v in variables)
                             for label, variables in trackers.items()},
                ))

        # Решение первой фазы забираем СРАЗУ, а не пересчитываем потом.
        # Пересчёт после снятия целевой функции оказался ненадёжным: на школе
        # из 28 классов с бюджетом 30 с он возвращал UNKNOWN и ноль уроков,
        # хотя законное расписание было найдено за две секунды. Теперь оно
        # просто лежит в кармане на случай, если улучшение не успеет.
        if first in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            fallback = [
                Lesson(slot=slot, group_id=item.group_id, subject_id=item.subject_id,
                       teacher_id=item.teacher_id, room_id=item.room_id, kind=item.kind)
                for i, item in enumerate(school.load)
                for slot in slots if solver.Value(x[i, slot])
            ]

        objective = sum(var * weight for var, weight in penalties)
        reporter = _Reporter(dict(trackers), max_seconds, on_progress, should_stop, started_at)
        gap_vars = trackers.get("Окна у учителей") or []

        if hierarchical and gap_vars:
            # ДВА КРИТЕРИЯ ПО ОЧЕРЕДИ, а не одной суммой.
            #
            # ⚠️ ВЫКЛЮЧЕНО ПО УМОЛЧАНИЮ. Замерено 25.08.2026, по два прогона
            # каждого режима на 28 классах (окон у учителей, меньше — лучше):
            #     одна сумма — 92 и 86
            #     по этапам  — 89 и 105
            # Выигрыша нет, разброс между прогонами больше разницы между
            # режимами, и этапы стабильно вылезают за отведённое время.
            # Код оставлен: на другой школе с другим соотношением ограничений
            # может выйти иначе — но включать это надо с замером, а не на веру.
            #
            # Взвешенная сумма заставляет солвер размазывать усилия: он одинаково
            # готов убрать окно у учителя и подровнять день у класса, хотя окно —
            # это час человека в школе без дела, а неровный день переживаем.
            # Поэтому сперва отдельно выжимаем окна, а потом фиксируем достигнутое
            # с небольшим допуском и на остаток времени доводим всё остальное.
            first_share = 0.45
            left = max_seconds - (time.monotonic() - started_at)
            solver.parameters.max_time_in_seconds = max(5.0, left * first_share)
            model.Minimize(sum(gap_vars))
            stage = solver.Solve(model, reporter)
            if stage in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                best_gaps = sum(int(solver.Value(v)) for v in gap_vars)
                # Старые подсказки сначала СНЯТЬ. Повторный AddHint для той же
                # переменной добавляет вторую запись, и модель становится
                # невалидной: замерено 25.08.2026 — третий этап возвращал
                # MODEL_INVALID за ноль секунд, то есть полная оптимизация
                # не выполнялась вовсе, а наружу уходил результат первого этапа.
                model.ClearHints()
                for key, var in x.items():
                    model.AddHint(var, solver.Value(var))
                # Жёстко фиксировать достигнутое НЕЛЬЗЯ. Замерено 25.08.2026:
                # с ограничением «окон не больше найденного +15%» второй этап
                # доказывал оптимальность в этой клетке и выходил на 145-й
                # секунде из 300 — половина бюджета пропадала, а разброс дней
                # и трудность выходили хуже, чем у обычной суммы.
                # Поэтому первый этап работает как разгон: он даёт хорошую
                # стартовую точку по главному критерию, дальше поиск свободен.
                fallback = [
                    Lesson(slot=slot, group_id=item.group_id, subject_id=item.subject_id,
                           teacher_id=item.teacher_id, room_id=item.room_id, kind=item.kind)
                    for i, item in enumerate(school.load)
                    for slot in slots if solver.Value(x[i, slot])
                ]
            model.ClearObjective()

        model.Minimize(objective)
        # Остаток бюджета — по реальным часам. `solver.WallTime()` показывает
        # длительность ПОСЛЕДНЕГО вызова, а не всё потраченное время, и второй
        # этап из-за этого получал пять секунд вместо половины бюджета.
        solver.parameters.max_time_in_seconds = max(
            5.0, max_seconds - (time.monotonic() - started_at))
        status = solver.Solve(model, reporter)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE) and fallback:
            # Улучшить не успели — отдаём законное расписание из первой фазы.
            # Оно неоптимальное, но это несравнимо лучше пустого ответа.
            return SolveResult("FEASIBLE", fallback, solver.WallTime(), None)
    else:
        solver.parameters.max_time_in_seconds = max_seconds
        if on_progress:
            on_progress(Progress(stage="search", seconds=0.0, budget=max_seconds,
                                 solutions=0))
        status = solver.Solve(model)

    lessons: list[Lesson] = []
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        for i, item in enumerate(school.load):
            for slot in slots:
                if solver.Value(x[i, slot]):
                    lessons.append(
                        Lesson(
                            slot=slot,
                            group_id=item.group_id,
                            subject_id=item.subject_id,
                            teacher_id=item.teacher_id,
                            room_id=item.room_id,
                            kind=item.kind,
                        )
                    )

    penalty = int(solver.ObjectiveValue()) if (optimize and penalties and lessons) else None
    return SolveResult(solver.StatusName(status), lessons, solver.WallTime(), penalty, relaxed)


def assign_rooms(school: School, lessons: list[Lesson]) -> list[Lesson]:
    """Назначить конкретные кабинеты уже поставленным урокам.

    Солвер гарантировал только ёмкость (уроков химии в слоте не больше, чем
    кабинетов химии). Здесь раздаём конкретные номера — жадно, слот за слотом.
    Если ёмкость соблюдена, назначение всегда найдётся.

    Приоритет: закреплённый в нагрузке кабинет → домашний кабинет учителя →
    свободный кабинет нужного типа.
    """
    rooms_by_kind: dict = defaultdict(list)
    for room in school.rooms:
        rooms_by_kind[room.kind].append(room)
    subject_room = {s.id: s.required_room for s in school.subjects}
    # чем строка нагрузки переопределила тип кабинета (деление труда и т. п.)
    kind_of_lesson = {(i.group_id, i.subject_id): i.room_kind
                      for i in school.load if i.room_kind}
    home = {t.id: t.home_room_id for t in school.teachers if t.home_room_id}

    by_slot: dict[Slot, list[Lesson]] = defaultdict(list)
    for lesson in lessons:
        by_slot[lesson.slot].append(lesson)

    for slot, slot_lessons in by_slot.items():
        taken: set[str] = set()
        for lesson in slot_lessons:
            if lesson.room_id:
                taken.add(lesson.room_id)
        for lesson in slot_lessons:
            if lesson.room_id:
                continue
            kind = kind_of_lesson.get(
                (lesson.group_id, lesson.subject_id)) or subject_room.get(lesson.subject_id)
            candidates = rooms_by_kind.get(kind, [])
            preferred = home.get(lesson.teacher_id)
            if preferred and preferred not in taken and any(r.id == preferred for r in candidates):
                lesson.room_id = preferred
            else:
                free = next((r for r in candidates if r.id not in taken), None)
                lesson.room_id = free.id if free else None
            if lesson.room_id:
                taken.add(lesson.room_id)
    return lessons


# ---------------------------------------------------------------- объяснимость

RULE_TITLES = {
    "pe_two_days": "Физкультура не два дня подряд",
    "pe_edges": "Физкультура первым или последним уроком не чаще раза в неделю",
    "hard_subject_edges": "Трудный предмет на краю дня не чаще раза в неделю",
    "peak_days": "Пик нагрузки во вторник, среду или пятницу",
    "difficulty_balance": "Равномерность дней по трудности",
    "even_days": "Ровное число уроков в дне",
    "teacher_wishes": "Пожелания учителей",
}

# Пункт первоисточника — отдельно от названия: в подписи под переключателем
# он не мешает читать саму норму, но остаётся на виду, когда завучу нужно
# сослаться на документ в разговоре с учителем.
RULE_SOURCES = {
    "pe_two_days": "п. 94 ССЭТ № 525",
    "pe_edges": "п. 94 ССЭТ № 525",
    "hard_subject_edges": "п. 94 ССЭТ № 525",
    "peak_days": "п. 94 ССЭТ № 525",
    "difficulty_balance": "п. 88.2 СанПиН № 206",
    "even_days": "не норма, а качество расписания. «Мягко» — коридор с допуском "
                  "в один урок, расписание находится всегда. «Жёстко» — идеальная "
                  "ровность, но поиск тяжелеет и решения может не быть",
    "teacher_wishes": "не норма, а договорённости внутри школы",
}


# Человеческие названия типов кабинетов живут в tables.py (там же, где их
# показывает интерфейс). Импорт локальный: solve.py не должен зависеть от слоя
# таблиц ради одной подписи в тексте ошибки.
def _room_kind_names() -> dict:
    from .tables import KIND_BY_VALUE
    return KIND_BY_VALUE


def diagnose(
    school: School,
    shift: Shift = Shift.FIRST,
    rules: Rules | None = None,
    max_seconds: float = 20.0,
    total_seconds: float | None = None,
) -> list[str]:
    """Почему расписание не сошлось.

    Голое INFEASIBLE — худший ответ, который можно дать завучу: он не говорит
    ничего и не подсказывает, что править (docs/domain.md §4.8). Поэтому при
    неудаче мы выясняем причину экспериментом: снимаем все нормы и пробуем
    снова. Если без норм расписание есть — значит дело в них, и мы включаем
    их по одной, пока не найдём ту, которая ломает. Если и без норм нет —
    проблема в данных: часов больше, чем места в сетке.

    Возвращает список фраз для человека, а не коды ошибок.
    """
    rules = rules or Rules()
    active = [name for name in RULE_TITLES if rules.is_hard(name)]

    # Общий предел на весь разбор. Каждая проба соблюдает свой лимит, но проб
    # много, а на большой школе САМА СБОРКА модели занимает заметное время
    # и повторяется на каждой — на гимназии в 28 классов разбор из шести проб
    # растянулся на 16 минут при лимите в 40 секунд на пробу. Для завуча это
    # то же самое, что зависание. Поэтому разбор смотрит на часы и, когда время
    # вышло, честно отдаёт найденное вместо того, чтобы продолжать.
    started = time.monotonic()
    budget = total_seconds if total_seconds is not None else max_seconds * 5

    def out_of_time() -> bool:
        return time.monotonic() - started > budget

    bare = Rules(**{name: "off" for name in RULE_TITLES})
    without = solve(school, shift, max_seconds, optimize=False, rules=bare)
    if without.status == "INFEASIBLE":
        return [
            "Дело не в санитарных нормах: расписание не складывается даже без них.",
            "Обычно это значит, что часов в нагрузке больше, чем уроков в сетке, "
            "или у кого-то из учителей слишком много недоступных слотов.",
        ]
    if not without.ok:
        # Даже без единой нормы не успели — значит виновата не норма, а время.
        # Обвинять здесь что-либо нельзя: мы просто ничего не выяснили.
        return [
            "За отведённое время причину выяснить не удалось: расписание не нашлось "
            "даже при полностью снятых нормах, а это обычно вопрос времени, "
            "а не запретов.",
            "Увеличьте время на поиск и запустите составление ещё раз.",
        ]

    # Кабинетный фонд — вторая частая причина после норм, и на неё почти никогда
    # не думают. Простой арифметикой её не поймать: по неделе кабинетов хватает,
    # а нерешаемость возникает в пиковый час, когда все классы учатся сразу
    # (класс занимается без окон, значит на первом уроке заняты все).
    # Проверяем экспериментом: снимаем кабинеты, оставляя нормы как есть.
    # Найдено 25.08.2026 на гимназии в 28 классов: 17 обычных кабинетов
    # на 28 классов — расписания не существует, и никакое время не помогает.
    # Причина редко бывает одна: переограниченная задача обычно упирается
    # сразу в несколько узких мест, и снятие любого из них её развязывает.
    # Поэтому собираем ВСЕ найденные выходы и показываем их вместе — выбирать,
    # что школе дешевле (добавить кабинет или ослабить норму), должен завуч,
    # а не порядок проверок в коде. Первая версия останавливалась на кабинетах
    # и заявляла «дело в них, а не в нормах», хотя снятие нормы о трудных
    # предметах развязывало ту же гимназию за 9 секунд.
    ways: list[list[str]] = []

    if not out_of_time() and solve(school, shift, max_seconds, optimize=False,
                                   rules=rules, ignore_rooms=True).ok:
        from collections import Counter
        have = Counter(room.kind for room in school.rooms)
        subject_room = {s.id: s.required_room for s in school.subjects}
        need = Counter()
        for item in school.load:
            need[item.room_kind or subject_room.get(item.subject_id)] += item.hours_per_week
        tight = sorted(need, key=lambda k: -(need[k] / max(1, have.get(k, 0))))
        titles = _room_kind_names()
        names = {kind: titles.get(kind.value, kind.value) for kind in need}
        worst = ", ".join(
            f"«{names[kind]}» — {have.get(kind, 0)} шт. на {need[kind]} ч"
            for kind in tight[:3] if kind is not None
        )
        ways.append([
            "**Кабинетов не хватает.** Со снятым ограничением по кабинетам "
            "расписание находится, а с ним — нет.",
            f"Всего кабинетов {len(school.rooms)} на {len(school.classes)} классов. "
            "Класс учится без окон, поэтому на первом уроке заняты все классы сразу — "
            "и кабинетов нужно столько же, сколько классов, плюс отдельный кабинет "
            "каждой подгруппе при делении.",
            (f"Самые тесные: {worst}." if worst else ""),
            "Что делать: добавить кабинеты на вкладке «4. Кабинеты» или убрать "
            "деление на подгруппы там, где оно не обязательно.",
        ])

    # СНИМАЕМ ПО ОДНОЙ, а не включаем по одной. Разница решающая.
    #
    # Проверка «одна норма включена, остальные сняты» отвечает на вопрос
    # «выполнима ли норма сама по себе», а он почти всегда «да» — и разбор
    # заканчивался бесполезным «они конфликтуют вместе». Завучу от этого
    # ничего: непонятно, какую именно ослабить.
    #
    # Правильный вопрос обратный: «если убрать вот эту, а остальные оставить, —
    # сойдётся?» Если сойдётся, значит именно она и мешает. Проверено
    # 25.08.2026 на гимназии в 28 классов: со всеми нормами расписание
    # не находилось за 10 минут, без нормы о трудных предметах на краю дня
    # нашлось за 9 секунд. Прежний разбор эту норму назвать не мог в принципе.
    #
    # Бюджет каждой пробы небольшой намеренно: снятие виновной нормы развязывает
    # задачу, и решение находится сразу. Проба, которая не уложилась, — это
    # «не она», а не «не знаю».
    trial_seconds = max(10.0, max_seconds / 2)
    freed, unchecked = [], []
    for name in active:
        if out_of_time():
            unchecked.append(name)
            continue
        trial = Rules(**{n: getattr(rules, n) for n in RULE_TITLES} | {name: "off"})
        if solve(school, shift, trial_seconds, optimize=False, rules=trial).ok:
            freed.append(name)

    if freed:
        block = ["**Мешают санитарные требования.** Стоит снять любое из этих — "
                 "и расписание находится за секунды:"]
        block += [f"• {RULE_TITLES[name]}" for name in freed]
        block.append(
            "Это действующие нормы, а не дефект алгоритма. Что делать: переключить "
            "нужное на «мягко» на вкладке «Нормы». Расписание составится, а все "
            "нарушения будут показаны списком — чтобы вы знали, за что отвечаете."
        )
        ways.append(block)

    if ways and unchecked:
        ways.append([
            "Проверить успели не всё: на разбор отведено ограниченное время, "
            "и эти требования остались непроверенными — "
            + ", ".join(RULE_TITLES[n].lower() for n in unchecked) + ".",
        ])

    if ways:
        out = []
        if len(ways) > 1:
            out.append(
                f"Узких мест {len(ways)}, и развязать задачу можно любым из них. "
                "Выбирайте по тому, что школе проще:"
            )
        for block in ways:
            out += [line for line in block if line]
        return out

    # Ни одна норма поодиночке не развязала задачу — виновата их совокупность
    # либо объём данных. Проверяем, доказуема ли невозможность вообще.
    if solve(school, shift, max_seconds, optimize=False, rules=rules
             ).status == "INFEASIBLE":
        return [
            "Расписания с такими требованиями не существует — это доказано, "
            "а не «не успели найти».",
            "Ни одно требование по отдельности задачу не развязывает, значит "
            "мешает их сочетание. Ослабьте до «мягко» самое спорное для вашей "
            "школы — начните с трудных предметов на краю дня: их проще всего "
            "нарушить в одном-двух классах, чем перекраивать нагрузку.",
        ]

    return [
        "Однозначной причины найти не удалось: ни снятие отдельных норм, "
        "ни снятие ограничений по кабинетам задачу не развязали, а доказать "
        "невозможность за отведённое время солвер не успел.",
        "Практический путь: увеличьте время на поиск до 10–15 минут. "
        "Если и это не поможет — ослабьте до «мягко» норму о трудных предметах "
        "на первом и последнем уроке: на плотной сетке она ограничивает сильнее "
        "остальных, потому что лёгких предметов, которыми можно закрыть края "
        "дня, в старших классах мало.",
    ]
