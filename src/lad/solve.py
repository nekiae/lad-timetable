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
import threading
import time
from pathlib import Path
from dataclasses import dataclass, field, replace

from ortools.sat.python import cp_model

from .model import Lesson, Level, RoomKind, School, Shift, Slot


@dataclass
class Weights:
    """Веса штрафов — «цена» каждого нарушения SOFT в очках.

    Важны не абсолютные значения, а их соотношение. Окно у учителя дороже
    лишнего дня присутствия, потому что окно — это час в школе без дела,
    а лишний день — это дорога.
    """

    teacher_gap: int = 10  # SOFT-1: окно у учителя
    teacher_both_shifts: int = 12  # день в школе от первой смены до второй
    teacher_day: int = 3  # SOFT-3: каждый день присутствия учителя в школе
    class_imbalance: int = 2  # SOFT-5: разброс нагрузки класса по дням (в уроках)
    difficulty_imbalance: int = 4  # п. 88.2 СанПиН: разброс по БАЛЛАМ трудности
    teacher_wish: int = 6  # пожелание учителя («нежелательно», а не «не могу»)
    peak_day: int = 3  # п. 94 ССЭТ: пик нагрузки не в день работоспособности
    pe_rule: int = 8  # п. 94 ССЭТ: физкультура, если правило переведено в мягкие
    hard_subject_edge: int = 5  # п. 94 ССЭТ: трудный предмет на краю дня

    # Предпочтения школы сверх норм (экран «Составление» → «Предпочтения школы»).
    # None — взять из TUNING: так их крутит стенд замеров (bench/solver.py --tune).
    subject_spacing: int | None = None  # предмет на 2–3 ч не в соседние дни
    single_lesson_day: int | None = None  # учитель не едет в школу ради одного урока
    light_day: int = 0  # короткий день недели у классов (0 — не нужен)
    light_day_of_week: int = 5  # какой день короткий: 1 — понедельник … 5 — пятница
    late_hard: int = 0  # трудные предметы не с 6-го урока
    avoid_doubles: int = 0  # поменьше сдвоенных уроков, даже где норма их разрешает
    pe_first_period: int = 0  # физкультура не первым уроком


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


# ПРЕДПОЧТЕНИЯ ШКОЛЫ — ползунки на экране «Составление».
#
# Завуч не выставляет «вес 6»: он говорит, что важнее, когда всё сразу не выходит.
# Уровень умножает вес выбранного режима («Поровну», «Учителям удобнее»…):
# «Важно» — ровно вес режима, поэтому пока школа ничего не трогала, солвер
# ведёт себя как измерено. Для предпочтений, которых в режиме нет (короткий
# день и т. п.), «Важно» — это `reference`. Нормы всё равно закрываются первыми:
# предпочтения работают только на этапе удобства (см. solve()).
PREFERENCE_LEVELS = {0: 0.0, 1: 0.5, 2: 1.0, 3: 2.0}  # не важно / немного / важно / очень

PREFERENCES = [
    {"key": "teacher_gap", "group": "Учителям", "reference": 10, "default": 2,
     "title": "Меньше окон у учителей",
     "about": "Свободный урок посреди дня — час в школе без дела."},
    {"key": "teacher_day", "group": "Учителям", "reference": 3, "default": 2,
     "title": "Меньше выходов в школу",
     "about": "Уроки учителя собираются в меньшее число дней."},
    {"key": "single_lesson_day", "group": "Учителям", "reference": 5, "default": 2,
     "title": "Не приезжать ради одного урока",
     "about": "День, где у учителя единственный урок."},
    {"key": "teacher_wish", "group": "Учителям", "reference": 6, "default": 2,
     "title": "Учитывать «нежелательно» из пожеланий",
     "about": "«Не может» соблюдается всегда; здесь — насколько беречь «нежелательно»."},
    {"key": "class_imbalance", "group": "Классам", "reference": 2, "default": 2,
     "title": "Ровное число уроков по дням",
     "about": "Чтобы не было дня на 8 уроков рядом с днём на 5."},
    {"key": "light_day", "group": "Классам", "reference": 6, "default": 0,
     "title": "Короткий день недели",
     "about": "В выбранный день у классов на урок меньше обычного."},
    {"key": "subject_spacing", "group": "Классам", "reference": 6, "default": 2,
     "title": "Предмет не в соседние дни",
     "about": "Предмет на 2–3 часа в неделю — через день: успеть сделать домашнее."},
    {"key": "late_hard", "group": "Классам", "reference": 3, "default": 0,
     "title": "Трудные предметы — не в конце дня",
     "about": "Математика, языки, физика, химия — не с 6-го урока."},
    {"key": "avoid_doubles", "group": "Классам", "reference": 4, "default": 0,
     "title": "Поменьше сдвоенных уроков",
     "about": "Даже там, где норма их разрешает (повышенный уровень, труд)."},
    {"key": "pe_first_period", "group": "Классам", "reference": 4, "default": 0,
     "title": "Физкультура не первым уроком",
     "about": "Норма и так ограничивает край дня; здесь — стараться не ставить первым вовсе."},
    {"key": "peak_day", "group": "Трудность недели", "reference": 3, "default": 2,
     "title": "Пик трудности во вторник, среду или пятницу",
     "about": "Рекомендация п. 94 ССЭТ: понедельник не должен быть самым тяжёлым."},
    {"key": "difficulty_imbalance", "group": "Трудность недели", "reference": 4, "default": 2,
     "title": "Трудность ровно по дням",
     "about": "Рекомендация п. 88.2 СанПиН: баллы трудности распределены по неделе."},
]


def weights_from_prefs(base: "Weights", prefs: dict | None) -> "Weights":
    """Уровни предпочтений школы → веса штрафов поверх выбранного режима."""
    if not prefs:
        return base
    values: dict = {}
    for pref in PREFERENCES:
        level = prefs.get(pref["key"])
        if level is None:
            continue
        current = getattr(base, pref["key"])
        if current is None:  # берётся из TUNING — там и лежит «важно»
            current = TUNING.get(pref["key"])
        reference = current or pref["reference"]
        values[pref["key"]] = int(round(reference * PREFERENCE_LEVELS.get(int(level), 1.0)))
    if prefs.get("light_day_of_week"):
        values["light_day_of_week"] = int(prefs["light_day_of_week"])
    return replace(base, **values)


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


# Цена нарушения жёсткой нормы при составлении (см. limit() в solve).
# Выбрана так, чтобы одно нарушение стоило дороже любой разумной суммы
# мягких штрафов школы: окно у учителя — 10, выход в школу — 3.
NORM_PRIORITY_WEIGHT = 1000

# Сколько раз возобновлять фазу улучшения, если солвер вышел раньше бюджета.
# Ограничение чисто страховочное: обычно кругов один-два, цикл и так упирается
# во время. Нужно на случай, если солвер начнёт возвращаться мгновенно.
_MAX_IMPROVE_ROUNDS = 8


# РУЧКИ АЛГОРИТМА для замеров (bench/solver.py --tune ключ=значение).
# Значения по умолчанию — те, что прошли замер 14.09.2026 (5 из 5 без нарушений).
# Менять значение по умолчанию — только с цифрами стенда, а не на глаз.
TUNING: dict = {
    # Доля бюджета на черновик «ноль нарушений». Черновик останавливается сам,
    # когда доказал ноль, поэтому большая доля не отнимает время у доводки.
    "draft_share": 0.8,
    # Черновик учитывает и удобство (окна, ровность дней) со второстепенным весом,
    # а не только нормы. Цель — чтобы доводка стартовала не с 1242 окон.
    # Риск: без чистой цели «сумма нарушений» черновик не останавливается на нуле
    # сам и тратит всю свою долю бюджета. Кандидат, по умолчанию выключен.
    "draft_comfort": False,
    # Сначала расставлять физкультуру. Замер 14.09.2026: хвост черновика («1 → 0»)
    # держит «физкультура первым или последним уроком» — залы в пн/ср/пт забиты
    # целиком (72 урока на 72 места), и класс упирается в край дня. Самый дефицитный
    # ресурс принято решать первым: стратегия ветвления по урокам физкультуры.
    # Действует на воркер с фиксированным поиском из портфеля CP-SAT. Кандидат.
    "pe_decisions_first": False,
    # ЛОГИКА РАСПИСАНИЯ СВЕРХ НОРМ (lad/quality.py). Разобрано 14.09.2026 на сетке
    # с нулём нарушений: у 17 классов из 24 дни отличаются на 3 урока, у 6 классов
    # пик трудности в понедельник, 50 двухчасовых предметов в соседние дни,
    # 27 выходов учителя ради одного урока. Веса — «очки» рядом с окном учителя (10).
    # Вес штрафа за предмет на 2–3 часа в соседние дни (0 — выключено).
    # Включено 14.09.2026 по стенду (120 с, медианы), вместе с single_lesson_day:
    #   школа завуча, 3 сида: 2ч в соседние дни 43 → 31, день ради урока 27 → 18,
    #     окна 66 → 67, до нуля норм 27 → 21 с, нарушений 0 → 0;
    #   гимназия 28 кл., 2 сида: 2ч в соседние дни 58 → 48, день ради урока 34 → 26,
    #     окна 69 → 81 (сиды 70 и 92 — разброс), нарушений 2 → 2 (минимум данных).
    "subject_spacing": 6,
    # Вес штрафа за день учителя с единственным уроком (0 — выключено).
    "single_lesson_day": 5,
    # Множитель веса разброса дней у класса (Weights.class_imbalance = 2 проигрывает окну = 10).
    # ×4 эффекта не дал (16 → 15 классов с разницей в 3 урока): дни неровные из-за
    # залов — физкультура забивает пн/ср/пт с 1-го по 8-й урок. Оставлено ×1.
    "balance_x": 1.0,
    # Множитель веса «пик трудности не во вторник/среду/пятницу».
    "peak_x": 1.0,
    # Пересборка вокруг закреплённых (экран расписания): штраф за каждый урок,
    # ушедший со своего места. Без него пересборка ради удобства перетасовывала
    # почти всё: замер 15.09.2026 — переставлено 746 уроков из 838 ради одного
    # закреплённого. Вес сопоставим с окном учителя (10): урок двигается, только
    # если это реально что-то даёт.
    "stay_weight": 6,
}


# Метка ограничения в limit() → человеческое имя нормы. Метки ставятся ниже
# в _solve: pe2_ — два дня подряд, peedge_ — физкультура на краю дня,
# hsedge_ — трудный предмет на краю дня (все три — п. 94 ССЭТ № 525).
_NORM_TAGS = {
    "pe2_": "Физкультура два дня подряд",
    "peedge_": "Физкультура первым или последним уроком",
    "hsedge_": "Трудный предмет на краю дня",
}


def _norm_title(tag: str) -> str:
    return next((title for prefix, title in _NORM_TAGS.items() if tag.startswith(prefix)), "Другие нормы")


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
    # Этап конвейера solve(): "draft" — черновик, цель одна: ноль нарушений норм;
    # "polish" — доводка удобства. Нужен, чтобы показать, ЧТО солвер сейчас улучшает.
    phase: str = "polish"
    # Снимок лучшей сетки: [строка нагрузки, день, урок] на каждый поставленный урок.
    # Не на каждое решение, а не чаще раза в секунду — см. _Reporter.
    grid: list[list[int]] | None = None
    # Нарушения по каждой норме отдельно — чтобы видеть, КАКАЯ норма держит хвост
    # поиска («1 → 0» тянется десятки секунд), а не одно общее число.
    norms: dict[str, int] = field(default_factory=dict)

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
                 on_progress, should_stop, started_at: float,
                 phase: str = "polish", grid_vars: list | None = None,
                 norm_detail: dict | None = None):
        super().__init__()
        self._trackers = trackers
        self._norm_detail = norm_detail or {}
        self._budget = budget
        self._on_progress = on_progress
        self._should_stop = should_stop
        self._started = started_at
        self._phase = phase
        self._grid_vars = grid_vars or []
        self._last_grid = 0.0
        self.solutions = 0

    def on_solution_callback(self) -> None:
        self.solutions += 1
        metrics = {}
        for label, variables in self._trackers.items():
            try:
                metrics[label] = sum(int(self.Value(v)) for v in variables)
            except Exception:
                continue
        # Снимок сетки — не чаще раза в секунду. Прочитать 17 тысяч переменных
        # дёшево, но решения в начале поиска сыплются десятками в секунду, и
        # слать каждую сетку в браузер значит тормозить и солвер, и страницу.
        grid = None
        now = time.monotonic()
        if self._on_progress and self._grid_vars and (self.solutions == 1 or now - self._last_grid >= 1.0):
            grid = [[i, slot.day, slot.period] for i, slot, var in self._grid_vars if self.Value(var)]
            self._last_grid = now
        if self._on_progress:
            self._on_progress(Progress(
                stage="improve",
                seconds=time.monotonic() - self._started,
                budget=self._budget,
                solutions=self.solutions,
                penalty=int(self.ObjectiveValue()) if self._trackers else None,
                bound=int(self.BestObjectiveBound()) if self._trackers else None,
                metrics=metrics,
                phase=self._phase,
                grid=grid,
                norms={title: sum(int(self.Value(v)) for v in variables)
                       for title, variables in self._norm_detail.items()},
            ))
        if self._should_stop and self._should_stop():
            self.StopSearch()


def _norm_violations(school: School, lessons: list[Lesson]) -> int | None:
    """Сколько нарушений норм в сетке — тем же валидатором, что считает отчёт."""
    if not lessons:
        return None
    from .validate import check  # локально: validate не нужен солверу, кроме этого случая
    return len(check(school, lessons).norm_violations)


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


def _solve(
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
    soft_norms: bool = False,
    norms_only: bool = False,
    norm_cap: int | None = None,
    phase: str = "polish",
    stay: list[Lesson] | None = None,
    stay_weight: int = 0,
    hint: list[Lesson] | None = None,
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
    norm_detail: dict[str, list] = defaultdict(list)  # норма → переменные превышения

    # --- переменные: x[i, slot] = 1, если i-я строка нагрузки стоит в этом слоте
    x: dict[tuple[int, Slot], cp_model.IntVar] = {}
    for i, item in enumerate(school.load):
        for slot in slots:
            x[i, slot] = model.NewBoolVar(f"x_{i}_{slot}")

    x_slots = set(slots)

    # --- СМЕНЫ. Ось уроков в дне общая для всей школы, а класс живёт в окне
    # своей смены: первая — уроки 1–8, вторая — 7–12, и седьмой урок у них
    # общий по времени. Так учитель, работающий в обеих сменах, не может
    # оказаться в двух местах, а кабинет второй смены освобождается первой.
    # Отдельный прогон на каждую смену этого бы не дал.
    row_window: dict[int, tuple[int, int]] = {}
    for i, item in enumerate(school.load):
        starts, ends = [], []
        for class_id in school.group(item.group_id).class_ids:
            start, end = school.class_window(class_id)
            starts.append(start)
            ends.append(end)
        row_window[i] = (max(starts or [1]), min(ends or [school.periods_per_day]))
    if any(w != (1, school.periods_per_day) for w in row_window.values()):
        for i, (start, end) in row_window.items():
            for slot in slots:
                if not start <= slot.period <= end:
                    model.Add(x[i, slot] == 0)

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

    # --- подсказка: готовая сетка, от которой поиск стартует (см. solve()).
    # Не ограничение — солвер волен уйти от неё, если она нарушает запреты.
    if hint:
        rows: dict[tuple[str, str, str], list[int]] = defaultdict(list)
        for i, item in enumerate(school.load):
            rows[item.group_id, item.subject_id, item.teacher_id].append(i)
        hinted = set()
        for lesson in hint:
            for i in rows.get((lesson.group_id, lesson.subject_id, lesson.teacher_id), [])[:1]:
                hinted.add((i, lesson.slot))
        for key, var in x.items():
            model.AddHint(var, 1 if key in hinted else 0)

    # --- «оставить на месте»: урок, ушедший из своей клетки, — штраф stay_weight
    # (см. TUNING["stay_weight"]). moved ≥ 1 − x: ограничено только снизу,
    # штраф сам опустит переменную, где урок остался.
    moved_vars: list = []
    if stay and stay_weight:
        stay_rows: dict[tuple[str, str, str], list[int]] = defaultdict(list)
        for i, item in enumerate(school.load):
            stay_rows[item.group_id, item.subject_id, item.teacher_id].append(i)
        for n, lesson in enumerate(stay):
            rows_of = stay_rows.get((lesson.group_id, lesson.subject_id, lesson.teacher_id))
            if not rows_of or lesson.slot not in x_slots:
                continue
            moved = model.NewBoolVar(f"moved_{n}")
            model.Add(moved >= 1 - x[rows_of[0], lesson.slot])
            moved_vars.append(moved)

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
    subject_always_double = {s.id: s.always_double for s in school.subjects}
    for i, item in enumerate(school.load):
        group = school.group(item.group_id)
        parallel = max((class_parallels.get(c, 0) for c in group.class_ids), default=0)
        subject_name = names_of_subject.get(item.subject_id, "")
        двойной = school.norms.double_allowed(
            subject_name, parallel, item.level != Level.BASE)

        # «Всегда парой» — свойство предмета, заданное школой (труд), а не
        # разрешение нормы. Оно сильнее: не «можно два», а «либо два, либо ни
        # одного».
        всегда_парой = subject_always_double.get(item.subject_id, False) \
            and item.hours_per_week % 2 == 0
        двойной = двойной or всегда_парой

        by_day: dict[int, list] = defaultdict(list)
        for slot in slots:
            by_day[slot.day].append(x[i, slot])
        for day, day_vars in by_day.items():
            model.Add(sum(day_vars) <= (2 if двойной else 1))
            if двойной and school.norms.double_must_be_consecutive:
                for p1 in range(1, school.periods_per_day + 1):
                    for p2 in range(p1 + 2, school.periods_per_day + 1):
                        model.Add(x[i, Slot(day, p1, shift)] + x[i, Slot(day, p2, shift)] <= 1)
            if всегда_парой:
                # Ноль или два, но не один: одинокий урок труда школе не нужен.
                model.Add(sum(day_vars) != 1)

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
        by_part: dict[str, list[int]] = defaultdict(list)
        for i in indices:
            by_part[school.group(school.load[i].group_id).part or ""].append(i)
        if len(by_part) < 2 or any(len(v) > 1 for v in by_part.values()):
            continue
        # Подгруппы с РАЗНЫМ числом часов синхронизируются частично: уроки
        # меньшей группы обязаны попадать в часы большей. Профильная группа
        # берёт математику шесть часов, базовая четыре — и эти четыре стоят
        # внутри тех шести, а не в отдельных уроках. Иначе класс занимает
        # десять мест вместо шести, а у базовой группы появляются дыры,
        # которых никто не видит (найдено 21.09.2026 на Жемчужненской).
        # Требование «меньшая ⊆ большей» даёт и равенство, когда часы равны.
        ranked = sorted((v[0] for v in by_part.values()),
                        key=lambda i: school.load[i].hours_per_week, reverse=True)
        base, *rest = ranked
        for other in rest:
            for slot in slots:
                model.Add(x[other, slot] <= x[base, slot])

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

        # «Без окон» считается ВНУТРИ окна смены: у второй смены день
        # начинается не с первого урока оси, а с седьмого.
        first_period, last_period = school.class_window(class_id)
        for day in {s.day for s in slots}:
            for period in range(first_period, last_period):
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
    subject_strict = {s.id: s.room_strict for s in school.subjects}

    def seats(kind) -> int:
        """Сколько уроков помещается в кабинеты этого типа ОДНОВРЕМЕННО.

        Не число комнат: спортзал держит два класса сразу, с двумя учителями.
        """
        return sum(max(1, room.parallel_classes) for room in rooms_by_kind.get(kind, []))

    # Строгие предметы (физкультура, информатика, труд) считаются по своему
    # типу кабинета. Нестрогие (физика, химия, биология) — вместе с обычными:
    # свой кабинет им желателен, но урок идёт и в классной комнате, а кто
    # сегодня в лаборатории, решается уже при раздаче кабинетов.
    load_by_kind: dict = defaultdict(list)
    shared: list[int] = []          # претенденты на «свой ИЛИ обычный»
    shared_kinds: set = set()
    for i, item in enumerate(school.load):
        if item.room_id:
            continue  # кабинет закреплён жёстко — обрабатываем ниже
        kind = item.room_kind or subject_room.get(item.subject_id)
        if kind is None:
            continue
        strict = subject_strict.get(item.subject_id, True) or item.room_kind is not None
        if strict or kind == RoomKind.REGULAR:
            load_by_kind[kind].append(i)
        else:
            shared.append(i)
            shared_kinds.add(kind)

    if not ignore_rooms:
        for kind, indices in load_by_kind.items():
            capacity = seats(kind)
            if capacity == 0:
                # Предмет требует кабинета, которого в школе нет. Не молчим:
                # это ошибка данных, а не невыполнимая задача.
                print(f"  ⚠️  нет ни одного кабинета типа {kind.value} — "
                      f"ограничение не наложено")
                continue
            for slot in slots:
                model.Add(sum(x[i, slot] for i in indices) <= capacity)

        # Общий пул: обычные кабинеты плюс те спецкабинеты, чьи предметы
        # согласны идти в обычный. Уроки конкурируют за него все вместе.
        if shared:
            pool = seats(RoomKind.REGULAR) + sum(seats(k) for k in shared_kinds)
            together = shared + load_by_kind.get(RoomKind.REGULAR, [])
            for slot in slots:
                model.Add(sum(x[i, slot] for i in together) <= pool)

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
    spacing_weight = int(w.subject_spacing if w.subject_spacing is not None else TUNING["subject_spacing"])
    single_weight = int(w.single_lesson_day if w.single_lesson_day is not None else TUNING["single_lesson_day"])
    days = sorted({s.day for s in slots})
    penalties = []  # (переменная, вес)
    for moved in moved_vars:
        penalties.append((moved, stay_weight))
        trackers["Переставлено уроков"].append(moved)
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
    # СМЕНЫ. Окно считается ВНУТРИ смены, а не сквозь весь день. Учитель
    # с уроком на 2-м (первая смена) и на 10-м (вторая) сидит не «семь часов
    # без дела»: между сменами он уходит. Сквозной подсчёт давал ему семь окон,
    # солвер бросался их лечить и ломал всё остальное — на Жемчужненской это
    # стоило сотни окон вместо семидесяти (21.09.2026).
    # Настоящая цена тут другая — «пришёл к восьми, ушёл в семь вечера», —
    # и она берётся отдельным штрафом teacher_both_shifts, один раз за день.
    shift_of_class = {c.id: int(c.shift) for c in school.classes}
    windows_by_shift = {sh: school.window(Shift(sh)) for sh in set(shift_of_class.values())}
    several_shifts = len(windows_by_shift) > 1

    def rows_of_shift(indices: list[int], sh: int) -> list[int]:
        if not several_shifts:
            return indices
        return [i for i in indices
                if any(shift_of_class.get(cid) == sh
                       for cid in school.group(school.load[i].group_id).class_ids)]

    for teacher_id, indices in by_teacher.items():
        for day in days:
          works_in_shift = {}
          day_gaps = []
          for sh, (win_from, win_to) in sorted(windows_by_shift.items()):
            mine = rows_of_shift(indices, sh)
            if not mine:
                continue
            periods = list(range(win_from, win_to + 1))
            tag = f"{teacher_id}_{day}_см{sh}"
            t_busy, started, rest, present = {}, {}, {}, {}
            for period in periods:
                slot = Slot(day, period, shift)
                busy_var = model.NewBoolVar(f"tb_{tag}_{period}")
                model.AddMaxEquality(busy_var, [x[i, slot] for i in mine])
                t_busy[period] = busy_var
                started[period] = model.NewBoolVar(f"st_{tag}_{period}")
                rest[period] = model.NewBoolVar(f"rs_{tag}_{period}")
                present[period] = model.NewBoolVar(f"pres_{tag}_{period}")

            for period in periods:
                model.Add(started[period] >= t_busy[period])
                model.Add(rest[period] >= t_busy[period])
                if period > win_from:
                    model.Add(started[period] >= started[period - 1])
                if period < win_to:
                    model.Add(rest[period] >= rest[period + 1])
                # в школе = начал и ещё не закончил
                model.Add(present[period] >= started[period] + rest[period] - 1)

            works = model.NewBoolVar(f"works_{tag}")
            for period in periods:
                model.Add(works >= t_busy[period])
            works_in_shift[sh] = (works, t_busy)

            gaps = model.NewIntVar(0, win_to - win_from + 1, f"gaps_{tag}")
            model.Add(gaps == sum(present.values()) - sum(t_busy.values()))
            penalties.append((gaps, w.teacher_gap))
            trackers["Окна у учителей"].append(gaps)
            day_gaps.append(gaps)

          if not works_in_shift:
            continue

          # Потолок дневной нагрузки — на ДЕНЬ целиком, а не на смену:
          # восемь уроков подряд тяжелы независимо от того, в какую смену они
          # стоят. Без потолка система, экономя учителю выходы в школу,
          # соберёт ему полный день.
          cap = teacher_by_id[teacher_id].max_per_day
          if cap:
              model.Add(sum(x[i, Slot(day, period, shift)] for i in indices
                            for period in range(1, school.periods_per_day + 1)) <= cap)

          # День в школе — один, даже если учитель работал в обеих сменах.
          day_busy = [v for _, busy in works_in_shift.values() for v in busy.values()]
          works_day = model.NewBoolVar(f"worksday_{teacher_id}_{day}")
          for var in day_busy:
              model.Add(works_day >= var)
          penalties.append((works_day, w.teacher_day))  # SOFT-3: меньше дней в школе
          trackers["Выходы в школу"].append(works_day)

          # Работа в обе смены: пришёл к восьми, ушёл в семь вечера. Это не
          # окна (между сменами учитель уходит), но и не бесплатно, поэтому
          # штраф отдельный и берётся один раз за день.
          if len(works_in_shift) > 1:
              both = model.NewBoolVar(f"both_{teacher_id}_{day}")
              for works, _ in works_in_shift.values():
                  model.Add(both <= works)
              model.Add(both >= sum(works for works, _ in works_in_shift.values())
                        - len(works_in_shift) + 1)
              penalties.append((both, w.teacher_both_shifts))
              trackers["Дней в обе смены"].append(both)

          # Выход в школу ради одного урока. single ≥ 2·works − уроков:
          # 0 уроков → 0, 1 урок → 1, два и больше → не больше нуля. Ограничено
          # только снизу — штраф сам опустит переменную, где урок не один.
          if single_weight:
              single = model.NewBoolVar(f"single_{teacher_id}_{day}")
              model.Add(single >= 2 * works_day - sum(day_busy))
              penalties.append((single, single_weight))
              trackers["Дней ради одного урока"].append(single)

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
        # Потолок дня — длина окна СВОЕЙ смены, а не всей оси: вторая смена
        # учится шесть уроков, сколько бы их ни было в дне у первой.
        win_from, win_to = school.class_window(class_id)
        high = min(high, win_to - win_from + 1)

        # Короткий день недели (предпочтение школы): в выбранный день — на урок
        # меньше обычного. Цель достижима: нижняя граница коридора дня тоже low − 1.
        if w.light_day and w.light_day_of_week in days and total:
            target = max(1, low - 1)
            extra = model.NewIntVar(0, school.periods_per_day, f"light_{class_id}")
            model.Add(extra >= per_day[days.index(w.light_day_of_week)] - target)
            penalties.append((extra, w.light_day))
            trackers["Короткий день: лишних уроков"].append(extra)

        if total and rules.on("even_days") and low <= high:
            # Жёсткая граница шире идеала на урок в каждую сторону, а к идеалу
            # тянет штраф. Идеальный коридор «ровно 5–6» оказался неподъёмным:
            # на 28 классах поиск ЛЮБОГО расписания стал нестабильным — то 10
            # секунд, то не находит за 45 вовсе (замерено 25.08.2026, три прогона
            # из трёх разошлись). Допуск в один урок возвращает солверу свободу,
            # а штраф всё равно приводит дни к 5–6: разброс по школе остаётся
            # тем же, но результат появляется всегда.
            # Допуск был симметричным — и стал нормой. При 33 уроках коридор
            # «6–7» превращался в разрешённые 5–8, а штраф в 16 очков солвер
            # охотно платил, лишь бы сэкономить пару окон учителю (10 очков
            # за окно). Получались дни 5 и 8 у одного класса — ровно то,
            # против чего коридор и вводился (найдено 22.09.2026 на 9«Г»).
            #
            # ПОЛ КОРИДОРА. Допуск вниз («можно на урок меньше идеала») был
            # симметричным — и стал нормой: солвер охотно платил 16 очков,
            # чтобы сэкономить учителю пару окон, и у класса выходил день
            # на 5 рядом с днём на 8. Убрать допуск целиком нельзя: школа
            # из примера тогда не считается вовсе, ни одной сетки за 120 с
            # (проверено 22.09.2026, как и предупреждал замер 25.08).
            # Поднять цену допуска — тоже не выход: поиск тонет, первая сетка
            # уходит с 2 до 55 секунд.
            # Убрать допуск насовсем — значит потерять школы, которые его
            # не держат. Включать автоматически — значит тратить время
            # на неудачные попытки там же. Поэтому допуск остаётся, а выбор
            # отдан завучу: режим «Ровные дни: жёстко» даёт идеальный коридор
            # без допуска, и на Жемчужненской это разброс 20 вместо 34.
            hard_low = max(1, low - 1)
            hard_high = min(win_to - win_from + 1, high + 1)
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
                # которого коридор и вводился. Второй урок сверх коридора
                # штрафуется вчетверо: один лишний урок — мелочь, два —
                # это уже день на восемь рядом с днём на пять.
                penalties.append((short, w.class_imbalance * 8))
                penalties.append((over, w.class_imbalance * 8))
                far = model.NewIntVar(0, school.periods_per_day, f"far_{count.Name()}")
                model.Add(far >= count - high - 1)
                penalties.append((far, w.class_imbalance * 24))
                # ...и день короче идеала на два урока — тоже день впустую.
                barely = model.NewIntVar(0, school.periods_per_day, f"barely_{count.Name()}")
                model.Add(barely >= low - 1 - count)
                penalties.append((barely, w.class_imbalance * 24))

        day_max = model.NewIntVar(0, school.periods_per_day, f"max_{class_id}")
        day_min = model.NewIntVar(0, school.periods_per_day, f"min_{class_id}")
        model.AddMaxEquality(day_max, per_day)
        model.AddMinEquality(day_min, per_day)

        spread = model.NewIntVar(0, school.periods_per_day, f"spread_{class_id}")
        model.Add(spread == day_max - day_min)
        penalties.append((spread, max(1, round(w.class_imbalance * float(TUNING["balance_x"])))))
        trackers["Разброс дней"].append(spread)

    parallels = {c.id: c.parallel for c in school.classes}
    subject_names = {s.id: s.name for s in school.subjects}

    # Представитель деления: подгруппы стоят в одних и тех же часах, поэтому
    # штраф за «предмет в соседние дни», «трудный предмет поздно» и прочее
    # берётся ОДИН раз — по строке с наибольшим числом часов (её слоты
    # покрывают слоты остальных, см. HARD-9). Раньше представителем считалась
    # подгруппа с именем «1», и все деления с осмысленными именами — «мальчики»,
    # «базовая» — выпадали из этих штрафов целиком (21.09.2026).
    representative: set[int] = set()
    best_of_split: dict[tuple[tuple[str, ...], str], int] = {}
    for i, item in enumerate(school.load):
        group = school.group(item.group_id)
        if group.part is None:
            representative.add(i)
            continue
        key = (tuple(group.class_ids), item.subject_id)
        current = best_of_split.get(key)
        if current is None or item.hours_per_week > school.load[current].hours_per_week:
            best_of_split[key] = i
    representative.update(best_of_split.values())

    # --- Разнесённость предмета по неделе (не норма — логика, lad/quality.py).
    # Предмет на 2–3 часа в соседние дни: литература в понедельник и сразу
    # во вторник — к завтрашнему уроку не подготовить домашнее. Предметам на
    # 4–5 часов соседние дни неизбежны, их не трогаем. Подгруппа «2» идёт
    # синхронно с «1», поэтому штраф берётся один раз — по первой.
    if spacing_weight:
        for i, item in enumerate(school.load):
            group = school.group(item.group_id)
            if item.hours_per_week not in (2, 3) or i not in representative:
                continue
            on_day = {}
            for day in days:
                var = model.NewBoolVar(f"on_{i}_{day}")
                model.AddMaxEquality(var, [x[i, s] for s in slots if s.day == day])
                on_day[day] = var
            for day, nxt in zip(days, days[1:]):
                if nxt != day + 1:
                    continue
                adjacent = model.NewBoolVar(f"adj_{i}_{day}")
                model.Add(adjacent >= on_day[day] + on_day[nxt] - 1)
                penalties.append((adjacent, spacing_weight))
                trackers["Предмет в соседние дни"].append(adjacent)

    # --- Предпочтения школы сверх норм: трудные не в конце дня, физкультура
    # не первым уроком, поменьше сдвоенных. Все три — только штрафы, по умолчанию 0.
    if w.late_hard or w.pe_first_period or w.avoid_doubles:
        always_pair = {s.id: s.always_double for s in school.subjects}
        for i, item in enumerate(school.load):
            group = school.group(item.group_id)
            if i not in representative:
                continue  # подгруппы стоят в одни часы — штраф один раз
            name = subject_names.get(item.subject_id, "")
            parallel = max((parallels.get(c, 0) for c in group.class_ids), default=0)
            if w.late_hard and school.norms.is_hard_subject(name) and parallel in school.norms.hard_parallels:
                for slot in slots:
                    if slot.period >= 6:
                        penalties.append((x[i, slot], w.late_hard))
                        trackers["Трудные предметы с 6-го урока"].append(x[i, slot])
            if w.pe_first_period and school.norms.is_pe(name):
                for slot in slots:
                    if slot.period == 1:
                        penalties.append((x[i, slot], w.pe_first_period))
                        trackers["Физкультура первым уроком"].append(x[i, slot])
            if (w.avoid_doubles and not always_pair.get(item.subject_id)
                    and school.norms.double_allowed(name, parallel, item.level != Level.BASE)):
                for day in days:
                    pair = model.NewIntVar(0, 1, f"dbl_{i}_{day}")
                    model.Add(pair >= sum(x[i, slot] for slot in slots if slot.day == day) - 1)
                    penalties.append((pair, w.avoid_doubles))
                    trackers["Сдвоенных уроков"].append(pair)

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
            class_first, class_last = school.class_window(class_id)
            for day in days:
                for period in range(class_first, class_last + 1):
                    var = model.NewBoolVar(f"last_{class_id}_{day}_{period}")
                    here = busy[class_id, Slot(day, period, shift)]
                    if period == class_last:
                        model.Add(var == here)
                    else:
                        nxt = busy[class_id, Slot(day, period + 1, shift)]
                        # var = here AND NOT nxt
                        model.Add(var <= here)
                        model.Add(var + nxt <= 1)
                        model.Add(var >= here - nxt)
                    last[class_id, day, period] = var

    def edge_count(indices: list[int], class_id: str, tag: str):
        """Сколько раз за неделю эти уроки стоят первыми или последними в дне.

        КОДИРОВКА — ОДНА ПЕРЕМЕННАЯ НА УРОК И ДЕНЬ, А НЕ НА УРОК, ДЕНЬ И НОМЕР.
        Прежняя версия заводила «урок i стоит на p-м И p-й последний» для
        каждого p с тремя ограничениями на каждую — на школе завуча это
        десятки тысяч переменных только на две нормы о краях дня. Замерено
        14.09.2026: без одной из них первое расписание находилось за 78 с,
        без другой не находилось за 120 с — именно они держали поиск.

        Теперь «урок i последний в этот день» — одна переменная, ограниченная
        СНИЗУ: она обязана быть 1, если урок стоит на p-м и p-й последний.
        Сверху её не держим: норма ограничивает число краёв сверху (запретом
        или штрафом), так что солвер сам опустит переменную в 0, когда урок
        не на краю. Двусторонняя связь для этого не нужна, а стоит втрое дороже.
        """
        terms = []
        class_first, class_last = school.class_window(class_id)
        for day in days:
            for i in indices:
                # первый урок дня — начало окна смены, а не всегда № 1
                terms.append(x[i, Slot(day, class_first, shift)])
                on_last = model.NewBoolVar(f"edge_{tag}_{i}_{day}")
                for period in range(class_first + 1, class_last + 1):
                    model.Add(on_last >= x[i, Slot(day, period, shift)]
                              + last[class_id, day, period] - 1)
                terms.append(on_last)
        return terms

    def limit(mode: str, terms: list, cap: int, weight: int, tag: str):
        """Применить ограничение «не больше cap» жёстко или через штраф."""
        if not terms:
            return
        if mode == "hard" and soft_norms:
            # ЖЁСТКАЯ НОРМА ПРИ СОСТАВЛЕНИИ — ЭТО ВЫСШИЙ ПРИОРИТЕТ, А НЕ ЗАПРЕТ.
            #
            # Замерено 14.09.2026 на школе завуча (24 класса, 838 часов), поиск
            # первого законного расписания:
            #     нормы запретами  — 185 с, 300+ с (не нашёл), 86 с
            #     нормы штрафами   — 1,1 с
            # Запрет режет пространство поиска так, что солвер минутами бродит
            # без единого решения, и завуч получает «не успел». Штраф в сотни раз
            # дороже всего остального даёт ту же иерархию — сперва ноль нарушений
            # норм, потом удобство, — но законная сетка есть с первой секунды.
            # Не довёл до нуля за бюджет — нарушения видны в отчёте поимённо.
            # Разбор причин (optimize=False) по-прежнему работает с запретами:
            # там нужен ответ «существует ли вообще».
            mode, weight = "soft", NORM_PRIORITY_WEIGHT
        if mode == "hard":
            model.Add(sum(terms) <= cap)
        else:  # soft: нарушение = превышение над cap, штрафуется
            over = model.NewIntVar(0, len(terms), f"over_{tag}")
            model.Add(over >= sum(terms) - cap)
            penalties.append((over, weight))
            trackers["Нарушений норм"].append(over)
            norm_detail[_norm_title(tag)].append(over)

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
            # ТРИ ЧАСА ПРИ ПЯТИДНЕВКЕ — ЭТО ПН, СР, ПТ, И МОДЕЛИ ЭТО ГОВОРИМ ПРЯМО.
            #
            # Если занятий ровно столько, сколько влезает без соседних дней,
            # а физкультура не бывает дважды в день (HARD-4b, сдваивать её
            # нельзя), расклад по дням единственный: через день, с первого.
            # Солвер вывел бы это и сам, но только перебором. Замерено
            # 14.09.2026 на школе завуча (24 класса, у всех по 3 часа, залы
            # вмещают 3 класса в час — 72 урока на 72 места): черновик за 120 с
            # застревал на 2–3 нарушениях «два дня подряд» во всех трёх прогонах,
            # остальные нормы сходились к нулю за секунды. Это не новое правило,
            # а следствие нормы, записанное явно.
            consecutive = days == list(range(days[0], days[0] + len(days)))
            once_a_day = not any(
                norms.double_allowed(subject_names.get(school.load[i].subject_id, ""),
                                     parallels.get(class_id, 0),
                                     school.load[i].level != Level.BASE)
                or subject_always_double.get(school.load[i].subject_id, False)
                for i in indices)
            if mode == "hard" and hours == room_for_pe and len(days) % 2 == 1 \
                    and consecutive and once_a_day:
                for day in days[1::2]:
                    for i in indices:
                        for s in slots:
                            if s.day == day:
                                model.Add(x[i, s] == 0)
            for day, nxt in zip(days, days[1:]):
                if nxt == day + 1:  # именно соседние дни недели
                    limit(mode, [pe_day[day], pe_day[nxt]], 1, w.pe_rule,
                          f"pe2_{class_id}_{day}")

    if rules.on("pe_edges") and norms.pe_max_first_or_last is not None:
        for class_id, indices in pe_indices.items():
            limit(rules.pe_edges, edge_count(indices, class_id, f"pe_{class_id}"),
                  norms.pe_max_first_or_last, w.pe_rule, f"peedge_{class_id}")

    if TUNING["pe_decisions_first"] and pe_indices:
        pe_rows = sorted({i for indices in pe_indices.values() for i in indices})
        model.AddDecisionStrategy([x[i, slot] for i in pe_rows for slot in slots],
                                  cp_model.CHOOSE_FIRST, cp_model.SELECT_MAX_VALUE)

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
                    penalties.append((excess, max(1, round(w.peak_day * float(TUNING["peak_x"])))))

    solver = cp_model.CpSolver()

    # «ОСТАНОВИТЬ» ДОЛЖНО РАБОТАТЬ В ЛЮБОЙ ФАЗЕ, А НЕ ТОЛЬКО МЕЖДУ РЕШЕНИЯМИ.
    # Раньше should_stop читал только колбэк найденного решения (_Reporter). В фазе
    # «найти первую сетку» колбэка нет, решений ещё нет — просьбу не слышал никто,
    # через 10 с сервер убивал процесс, и завуч получал «процесс завершился без
    # ответа» вместо лучшей сетки (сквозной прогон 15.09.2026). Наблюдатель раз
    # в полсекунды спрашивает should_stop и прерывает поиск: stop_search() в
    # OR-Tools безопасно звать из другого потока. Поток фоновый и заканчивается
    # сам — после первой остановки или вместе с процессом.
    if should_stop:
        def _watch_stop() -> None:
            while True:
                time.sleep(0.5)
                if should_stop():
                    solver.stop_search()
                    return

        threading.Thread(target=_watch_stop, daemon=True).start()
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

    # Потолок нарушений норм для доводки (см. solve()): удобство улучшаем,
    # но нормы на него не меняем. Ставится ДО первой фазы — иначе первая
    # найденная сетка может оказаться хуже черновика, от которого стартуем.
    if norm_cap is not None and trackers.get("Нарушений норм"):
        model.Add(sum(trackers["Нарушений норм"]) <= norm_cap)

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
                                 solutions=0, phase=phase))
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
            model.ClearHints()  # повторный AddHint без очистки делает модель невалидной
            for key, var in x.items():
                model.AddHint(var, solver.Value(var))
            if on_progress:
                on_progress(Progress(
                    stage="improve", seconds=time.monotonic() - started_at,
                    budget=max_seconds, solutions=1,
                    metrics={label: sum(int(solver.Value(v)) for v in variables)
                             for label, variables in trackers.items()},
                    phase=phase,
                    grid=[[i, slot.day, slot.period] for (i, slot), var in x.items()
                          if solver.Value(var)],
                    norms={title: sum(int(solver.Value(v)) for v in variables)
                           for title, variables in norm_detail.items()},
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

        if norms_only and trackers.get("Нарушений норм"):
            # Черновик: единственная цель — ноль нарушений норм (см. solve()).
            objective = sum(trackers["Нарушений норм"])
            if moved_vars:
                # При пересборке черновик ещё и бережёт сетку: сначала нормы,
                # из законных — та, где меньше уроков ушло со своих мест.
                objective = NORM_PRIORITY_WEIGHT * objective + sum(moved_vars)
        else:
            objective = sum(var * weight for var, weight in penalties)
        reporter = _Reporter(dict(trackers), max_seconds, on_progress, should_stop, started_at,
                             phase=phase, grid_vars=[(i, slot, var) for (i, slot), var in x.items()],
                             norm_detail=dict(norm_detail))
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

        # УЛУЧШАЕМ ДО КОНЦА БЮДЖЕТА, А НЕ ДО ПЕРВОЙ ОСТАНОВКИ СОЛВЕРА.
        #
        # CP-SAT иногда завершает поиск сам, задолго до лимита, со статусом
        # FEASIBLE — то есть без доказательства оптимальности. Замерено
        # 07.09.2026 на 28 классах, бюджет 300 с, одни и те же данные:
        #     прогон А — вторая фаза 291 с из 291, окон у учителей  38
        #     прогон Б — вторая фаза 166 с из 294, окон у учителей  52
        #     прогон В — вторая фаза  25 с из 279, окон у учителей 268
        # Разброс в семь раз при одинаковом вводе. Для демо это хуже, чем
        # медленно: нельзя нажать кнопку и не знать, что покажет экран.
        #
        # Поэтому после каждого возврата, если время ещё есть, перезапускаем
        # поиск от лучшего найденного (снимаем старые подсказки и ставим новые —
        # повторный AddHint для той же переменной делает модель невалидной).
        # Лучшее решение держим отдельно: следующий круг стартует с той же
        # точки, но пойти может хуже, и отдавать надо не последнее, а лучшее.
        best_lessons: list[Lesson] = []
        best_penalty: int | None = None
        status = cp_model.UNKNOWN
        rounds = 0
        while True:
            left = max_seconds - (time.monotonic() - started_at)
            if left < 5.0 or rounds >= _MAX_IMPROVE_ROUNDS:
                break
            rounds += 1
            solver.parameters.max_time_in_seconds = left
            round_started = time.monotonic()
            status = solver.Solve(model, reporter)
            if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                break
            value = int(solver.ObjectiveValue())
            if best_penalty is None or value < best_penalty:
                best_penalty = value
                best_lessons = [
                    Lesson(slot=slot, group_id=item.group_id, subject_id=item.subject_id,
                           teacher_id=item.teacher_id, room_id=item.room_id, kind=item.kind)
                    for i, item in enumerate(school.load)
                    for slot in slots if solver.Value(x[i, slot])
                ]
            if status == cp_model.OPTIMAL:
                break  # доказано лучшее — дальше искать нечего
            if should_stop and should_stop():
                break
            # Защита от холостого кручения: если солвер вернулся мгновенно,
            # следующий круг вернётся так же, и цикл только сожжёт бюджет.
            if time.monotonic() - round_started < 1.0:
                break
            model.ClearHints()
            for key, var in x.items():
                model.AddHint(var, solver.Value(var))

        if best_lessons:
            return SolveResult(
                "OPTIMAL" if status == cp_model.OPTIMAL else "FEASIBLE",
                best_lessons, time.monotonic() - started_at, best_penalty, relaxed)
        if fallback:
            # Улучшить не успели — отдаём законное расписание из первой фазы.
            # Оно неоптимальное, но это несравнимо лучше пустого ответа.
            return SolveResult("FEASIBLE", fallback, solver.WallTime(), None, relaxed)
    else:
        solver.parameters.max_time_in_seconds = max_seconds
        if on_progress:
            on_progress(Progress(stage="search", seconds=0.0, budget=max_seconds,
                                 solutions=0, phase=phase))
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
    hint: list[Lesson] | None = None,
    stay: list[Lesson] | None = None,
    settle: float | None = None,
) -> SolveResult:
    """Составить расписание. Всегда отдаёт сетку, если она в принципе существует.

    `settle` — остановить этап раньше бюджета, если нормы уже на нуле, а лучшего
    решения нет `settle` секунд. Пересборка вокруг закреплённых уроков иначе всегда
    ждала все 40 секунд, хотя сетка переставала меняться намного раньше.

    `hint` — готовая сетка, от которой начать (пересборка вокруг закреплённых
    уроков на экране расписания): черновик стартует не с пустого места, и
    законная сетка находится почти сразу. Это подсказка, а не ограничение.

    `stay` — сетка, которую надо сберечь: каждый урок, ушедший со своего места,
    штрафуется (TUNING["stay_weight"]). Так пересборка вокруг закреплённых
    двигает нужное, а не перетасовывает всё ради удобства.

    ПОЧЕМУ ДВА ШАГА. Замерено 14.09.2026 на школе завуча (24 класса, 838 часов):
      • нормы запретами — первое расписание за 185 с, 86 с, а в одном прогоне
        из трёх не нашлось за 5 минут вовсе («не успел»);
      • нормы штрафами — первое расписание за 1,1 с, но за 5 минут в сетке
        осталось 29 нарушений норм: удобство учителей и нормы тянули в разные
        стороны, и солвер разменивал одно на другое.

    Поэтому сначала ЧЕРНОВИК: нормы штрафом, а цель одна — ноль нарушений.
    Сетка есть с первой секунды, и все силы уходят на нормы. Потом черновик
    идёт подсказкой в доводку удобства, где нарушений норм не может стать
    больше, чем в черновике: при нуле это те же запреты, но старт не с пустого
    места, а с законной сетки.

    Если черновик до нуля не дошёл — нормы, скорее всего, в этой школе
    одновременно невыполнимы. Тогда отдаём лучшую сетку с поимённым списком
    нарушений, а не пустой экран.

    Разбор причин (optimize=False) идёт напрямую, с запретами: там нужен
    ответ «существует ли расписание вообще».
    """
    rules = rules or Rules()

    # Ранняя остановка по затишью: этап ведёт свой отсчёт — черновик и доводка
    # сравнивают штрафы разного смысла, поэтому при смене этапа отсчёт с нуля.
    # Просьба человека «Остановить» проверяется первой и остаётся главной.
    user_stop = should_stop
    settled = {"phase": None, "best": None, "at": time.monotonic(), "zero": False}
    if settle:
        user_progress = on_progress

        def on_progress(progress, _user=user_progress):  # noqa: F811 — обёртка над колбэком
            now = time.monotonic()
            if progress.phase != settled["phase"]:
                settled.update(phase=progress.phase, best=None, at=now)
            # Улучшением считается ЗАМЕТНОЕ: не меньше 1% штрафа. Доводка почти
            # непрерывно находит крошечные улучшения, и затишья не наступало
            # никогда — замер 16.09.2026: все прогоны доигрывали бюджет до конца.
            best = settled["best"]
            if progress.penalty is not None and (best is None
                                                 or progress.penalty <= best - max(1.0, abs(best) * 0.01)):
                settled.update(best=progress.penalty, at=now)
            # Ноль нарушений засчитывается, ТОЛЬКО если счётчик действительно
            # пришёл. Значение по умолчанию ноль останавливало черновик, где
            # такого счётчика нет: замер 16.09.2026 — settle=4 дал 24 нарушения
            # норм и 659 переставленных уроков вместо 0 и 10.
            norms = progress.metrics.get("Нарушений норм")
            settled["zero"] = norms == 0 if norms is not None else (
                bool(progress.norms) and sum(progress.norms.values()) == 0)
            if _user:
                _user(progress)

        def should_stop():  # noqa: F811
            if user_stop and user_stop():
                return True
            # ТОЛЬКО ДОВОДКА. Черновик всегда доигрывает свой бюджет: его счётчик
            # нарушений — модельный и расходится с валидатором, и остановка по
            # затишью ловила момент, когда модель считает, что нарушений нет.
            # Замеры 16.09.2026: 25 и 43 нарушения в готовой сетке. У доводки же
            # есть потолок нарушений, посчитанный валидатором по черновику, —
            # раньше времени она закончится, но хуже черновика не станет.
            return (settled["phase"] == "polish" and settled["zero"]
                    and time.monotonic() - settled["at"] >= settle)

    common = dict(shift=shift, weights=weights, rules=rules, should_stop=should_stop,
                  pinned=pinned, params=params, ignore_rooms=ignore_rooms)
    if not optimize or not any(rules.is_hard(name) for name in RULE_TITLES):
        return _solve(school, max_seconds=max_seconds, optimize=optimize,
                      on_progress=on_progress, hierarchical=hierarchical, **common)

    started = time.monotonic()

    def left() -> float:
        return max_seconds - (time.monotonic() - started)

    # Черновику — почти весь бюджет. Он останавливается сам, как только доказал
    # ноль нарушений (цель — сумма нарушений, ноль — нижняя граница), поэтому
    # лишнего не съест. Половины не хватало: замерено 14.09.2026, один сид из трёх
    # доходил до нуля только на 106-й секунде, а обёртка обрывала его на 60-й.
    # С `stay` черновик не останавливается на нуле сам (он ещё бережёт сетку),
    # поэтому доля его бюджета меньше — доводке нужно время уложить уроки назад.
    share = 0.6 if stay else float(TUNING["draft_share"])
    draft = _solve(school, max_seconds=max_seconds * share, optimize=True,
                   soft_norms=True, norms_only=not TUNING["draft_comfort"], on_progress=on_progress,
                   phase="draft", hint=hint, stay=stay, stay_weight=1 if stay else 0, **common)

    # «Ровные дни: жёстко» — идеальный коридор без допуска: дни выходят ровно
    # 6–7 вместо 5–8. Там, где школа его держит, он лучше по всем статьям
    # (Жемчужненская 22.09.2026: разброс 16 против 34, окна 33 против 41).
    # Там, где не держит, он раньше отдавал ПУСТОЙ ЭКРАН — завуч нажимал
    # переключатель и получал «расписание не находится» без объяснения
    # (школа из примера, тот же замер). Теперь режим сам отступает на «мягко»
    # и говорит об этом: строгость дней не стоит отсутствия расписания.
    if not draft.ok and rules.is_hard("even_days") and left() > 10:
        softer = replace(rules, even_days="soft")
        relaxed = dict(common, rules=softer)
        draft = _solve(school, max_seconds=left() * share, optimize=True,
                       soft_norms=True, norms_only=not TUNING["draft_comfort"],
                       on_progress=on_progress, phase="draft", hint=hint, stay=stay,
                       stay_weight=1 if stay else 0, **relaxed)
        if draft.ok:
            rules, common = softer, relaxed
            draft.relaxed = [*draft.relaxed,
                             "Ровное число уроков в дне — с допуском: без него "
                             "расписания у этой школы не существует"]
    if not draft.ok:
        return draft

    # Отсчёт затишья доводки — с её первого решения, а не с черновика: иначе
    # наблюдатель доводки остановил бы её через полсекунды, ещё без решений.
    settled.update(phase=None, best=None, at=time.monotonic(), zero=False)
    if not (user_stop and user_stop()) and left() > 5:
        # Доводка удобства — от черновика и с потолком «нарушений норм не больше,
        # чем в черновике». Без потолка доводка разменивала нормы на окна учителей:
        # замерено 14.09.2026 — прогон с 18 нарушениями на выходе. При нуле
        # в черновике потолок ноль — это те же запреты, но старт с законной сетки.
        # Потолок — РЕАЛЬНОЕ число нарушений в черновике, посчитанное валидатором.
        # Брать штраф черновика можно только когда он и есть «сумма нарушений».
        # При пересборке (stay) штраф — смесь «нарушения × вес» и «сколько уроков
        # сдвинулось», и потолок выходил огромным: доводка получала право наставить
        # нарушений. Замер 16.09.2026: 43 нарушения и 711 переставленных уроков.
        cap = (_norm_violations(school, draft.lessons)
               if (stay or TUNING["draft_comfort"]) else draft.penalty)
        polish = dict(optimize=True, soft_norms=True, norm_cap=cap,
                      on_progress=on_progress, hierarchical=hierarchical, stay=stay,
                      stay_weight=int(TUNING["stay_weight"]) if stay else 0, **common)
        # ПОЛ КОРИДОРА — попытка доводки, а не условие задачи. Жёсткий пол
        # («день не короче идеала») убирает у класса день на пять рядом с днём
        # на восемь, но не всякая школа его выдержит: на школе из примера
        # с ним не находится ничего. Спрашивать заранее пробой оказалось дорого
        # — на ту же школу это стоило десяти секунд и незакрытой нормы
        # (замер 22.09.2026). Поэтому пробуем на половине времени доводки,
        # и если не вышло — доводим обычным коридором. Черновик с его нормами
        # при этом не трогаем вовсе, так что платы за неудачу нет.
        # Пол коридора («день не короче идеала») пробовали включать
        # автоматически — отдельной пробой перед запуском и коротким подходом
        # внутри доводки. Оба способа отброшены 22.09.2026: неудачная попытка
        # съедает время у норм, и школа из примера возвращалась с незакрытой
        # нормой, а выигрыш на Жемчужненской скакал от сида к сиду.
        # Пол остаётся у режима «Ровные дни: жёстко» — им распоряжается завуч.
        final = _solve(school, max_seconds=left(), hint=draft.lessons, **polish)
        if final.ok:
            final.wall_time = time.monotonic() - started
            return final

    draft.wall_time = time.monotonic() - started
    draft.penalty = None  # штраф черновика считает только нормы, с итоговым несравним
    return draft


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
    subject_strict = {s.id: s.room_strict for s in school.subjects}
    # чем строка нагрузки переопределила тип кабинета (деление труда и т. п.)
    kind_of_lesson = {(i.group_id, i.subject_id): i.room_kind
                      for i in school.load if i.room_kind}
    home = {t.id: t.home_room_id for t in school.teachers if t.home_room_id}

    # КАБИНЕТ КЛАССА. Без него класс кочевал: замерено 14.09.2026 на школе завуча —
    # до 13 разных обычных кабинетов у одного класса за неделю, потому что комнаты
    # раздавались «первая свободная» слот за слотом. Завуч увидит это на первом же
    # листе печати. Теперь у каждого класса свой обычный кабинет — по порядку, пока
    # их хватает, — и его урокам он достаётся первым. При кабинетной системе
    # (у учителей свои кабинеты) классам кабинеты не закрепляем: там ходят дети.
    regular_rooms = rooms_by_kind.get(RoomKind.REGULAR, [])
    class_home = {} if home else {
        c.id: regular_rooms[n].id for n, c in enumerate(school.classes) if n < len(regular_rooms)}
    reserved = set(class_home.values())
    groups = {g.id: g for g in school.groups}
    last_room: dict[str, str] = {}  # учитель → кабинет его предыдущего урока

    def class_room(lesson) -> str | None:
        group = groups.get(lesson.group_id)
        if group and group.part is None and len(group.class_ids) == 1:
            return class_home.get(group.class_ids[0])
        return None

    by_slot: dict[Slot, list[Lesson]] = defaultdict(list)
    for lesson in lessons:
        by_slot[lesson.slot].append(lesson)

    # Считаем не «занят / свободен», а сколько классов кабинет ещё вмещает:
    # спортзал держит два урока сразу (Room.parallel_classes).
    room_by_id = {room.id: room for room in school.rooms}

    # По порядку недели: «кабинет предыдущего урока учителя» имеет смысл
    # только если предыдущий урок и правда был раньше.
    for slot in sorted(by_slot, key=lambda sl: (sl.shift, sl.day, sl.period)):
        slot_lessons = by_slot[slot]
        used: dict[str, int] = defaultdict(int)
        for lesson in slot_lessons:
            if lesson.room_id:
                used[lesson.room_id] += 1

        def has_place(room_id: str) -> bool:
            room = room_by_id.get(room_id)
            return used[room_id] < max(1, room.parallel_classes if room else 1)

        # Сначала те, кому кабинет обязателен: физкультуре нужен зал, и если
        # его займёт химия «просто так», уроку физкультуры идти будет некуда.
        def strictness(lesson) -> int:
            return 0 if subject_strict.get(lesson.subject_id, True) else 1

        # Хозяева кабинетов — раньше остальных, чтобы их комнату не заняли «просто так».
        for lesson in sorted(slot_lessons, key=lambda l: (strictness(l), class_room(l) is None)):
            if lesson.room_id:
                continue
            kind = kind_of_lesson.get(
                (lesson.group_id, lesson.subject_id)) or subject_room.get(lesson.subject_id)
            # Кабинет, заданный прямо в строке нагрузки, обсуждению не подлежит;
            # у остальных нестрогих предметов вторым вариантом идёт обычный.
            fixed = kind_of_lesson.get((lesson.group_id, lesson.subject_id)) is not None
            pool = [kind]
            if not fixed and not subject_strict.get(lesson.subject_id, True) \
                    and kind != RoomKind.REGULAR:
                pool.append(RoomKind.REGULAR)
            teacher = lesson.teacher_id
            # Свой кабинет учителя → кабинет класса → где учитель вёл прошлый урок.
            prefer = (home.get(teacher), class_room(lesson), last_room.get(teacher))

            def first_free(rooms) -> str | None:
                ids = [r.id for r in rooms]
                wanted = next((w for w in prefer if w and w in ids and has_place(w)), None)
                # Без предпочтения — сначала ничьи кабинеты, потом чужие закреплённые:
                # хозяин сейчас не здесь, но его комнату лучше не трогать.
                return wanted or next((i for i in ids if has_place(i) and i not in reserved), None) \
                    or next((i for i in ids if has_place(i)), None)

            # Сначала кабинет СВОЕГО типа. Замерено 14.09.2026: если пускать нестрогую
            # физику сразу в кабинет класса, она занимала его при свободном кабинете
            # физики, и на урезанном фонде без комнаты оставалось вдвое больше уроков
            # (48 против 24). Свой тип занят — нестрогий предмет идёт в обычный,
            # и лучше в кабинет своего класса, чем в случайный.
            lesson.room_id = first_free(rooms_by_kind.get(kind, []))
            if lesson.room_id is None and len(pool) > 1:
                lesson.room_id = first_free(rooms_by_kind.get(RoomKind.REGULAR, []))
            if lesson.room_id:
                used[lesson.room_id] += 1
                last_room[teacher] = lesson.room_id
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
                  "в один урок: у класса может выйти день на 5 уроков рядом с днём "
                  "на 8. «Жёстко» — дни ровные, по 6–7; если школа этого не "
                  "выдержит, система сама вернётся к допуску и скажет об этом. "
                  "Начинать стоит с «жёстко»",
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
            "Что делать: добавить кабинеты на шаге «Кабинеты» или убрать "
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
            "нужное на «мягко» на шаге «Проверка». Расписание составится, а все "
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
