"""«Что если»: одно изменение школы — и два расписания рядом, без него и с ним.

Завуч спрашивает: «а если Иванова уйдёт на курсы по средам?», «а если зал
возьмёт три класса?». Ответ «окон станет 60» ничего не значит сам по себе —
его надо сравнить. Но сравнивать с сохранённым расписанием нечестно: оно
искалось другое время, и часть разницы дал бы просто лишний поиск, а не
изменение (CP-SAT на тех же данных с разными сидами даёт окна 55–63).

Поэтому считаются ДВА варианта одновременно и одинаково: тот же старт, тот же
бюджет, те же настройки. Отличаются они только изменением — значит, и разница
между ними от изменения (правило честного сравнения, CLAUDE.md §8.3).

Изменение не трогает данные школы, пока завуч не нажмёт «Принять»: варианты
лежат в таблице расписаний с пометкой `change` и в «последнее расписание» не попадают.
"""

from __future__ import annotations

import copy
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import db
from .jobs import start_job

from lad.quality import measure  # noqa: E402
from lad.solve import PRESETS, RULE_TITLES, available_cpus  # noqa: E402
from lad.storage import lessons_from_dict  # noqa: E402
from lad.tables import build_school, tables_from_dict  # noqa: E402
from lad.validate import check  # noqa: E402

router = APIRouter(prefix="/api/schools/{school_id}/whatif")

DAY_NAMES = {1: "понедельник", 2: "вторник", 3: "среду", 4: "четверг", 5: "пятницу", 6: "субботу"}
ON_DAY = {d: ("во " if d == 2 else "в ") + name for d, name in DAY_NAMES.items()}
STRICT_NAMES = {"hard": "жёстко", "soft": "мягко", "off": "не учитывать"}
# Беречь текущее расписание — минута: старт с готовой сетки, солвер двигает
# только нужное. С нуля — две: законная сетка за секунды, остальное на удобство.
BUDGETS = {"keep": 60, "fresh": 120}


def apply_change(doc: dict, change: dict) -> tuple[dict, str]:
    """Копия документа школы с изменением и его человеческое название."""
    doc = copy.deepcopy(doc)
    settings = doc.setdefault("settings", {})
    kind = change.get("kind")

    if kind == "teacher_day_off":
        name, day = str(change.get("teacher") or ""), int(change.get("day") or 0)
        names = {str(t.get("ФИО", "")).strip() for t in doc["tables"].get("teachers", [])}
        if name not in names or day not in DAY_NAMES:
            raise HTTPException(422, "Выберите учителя и день")
        periods = int(settings.get("periods") or 8)
        wish = doc.setdefault("wishes", {}).setdefault(name, {"hard": [], "soft": []})
        hard = {tuple(slot) for slot in wish.get("hard", [])} | {(day, p) for p in range(1, periods + 1)}
        wish["hard"] = sorted([list(slot) for slot in hard])
        wish["soft"] = [slot for slot in wish.get("soft", []) if slot[0] != day]
        return doc, f"{name} не может {ON_DAY[day]}"

    if kind == "gym_plus":
        gyms = [room for room in doc["tables"].get("rooms", []) if room.get("тип") == "спортзал"]
        if not gyms:
            raise HTTPException(422, "В данных школы нет спортзала")
        for room in gyms:
            room["классов сразу"] = int(room.get("классов сразу") or 1) + 1
        return doc, "В спортзале одновременно на один класс больше"

    if kind == "preset":
        preset = str(change.get("preset") or "")
        if preset not in PRESETS:
            raise HTTPException(422, "Нет такого режима")
        settings["preset"] = preset
        return doc, f"Режим «{preset}»"

    if kind == "rule":
        key, value = str(change.get("rule") or ""), str(change.get("value") or "")
        if key not in RULE_TITLES or value not in STRICT_NAMES:
            raise HTTPException(422, "Выберите норму и строгость")
        settings["rules"] = {**(settings.get("rules") or {}), key: value}
        return doc, f"Норма «{RULE_TITLES[key]}» — {STRICT_NAMES[value]}"

    if kind == "aim":
        # Пожелание с адресом — то, что завуч выбрал в «Поправить» на готовой
        # сетке. Ложится в данные школы насовсем, поэтому сначала показываем
        # цену: сколько уроков переедет и что станет хуже.
        aim = change.get("aim") or {}
        key = str(aim.get("key") or "")
        if not key:
            raise HTTPException(422, "Пожелание без ключа")
        rows = [row for row in (doc.get("targeted") or [])
                if not (row.get("key") == key and row.get("scope") == aim.get("scope")
                        and row.get("who") == aim.get("who"))]
        doc["targeted"] = [*rows, aim]
        return doc, str(change.get("label") or "Новое пожелание школы")

    raise HTTPException(422, "Неизвестное изменение")


# Насколько широко разрешено ворошить сетку. Закреплять уроки руками нельзя:
# их восемьсот, а жёстко закреплённые полшколы делают задачу нерешаемой.
# Поэтому круг считает система, и если он тесен — сама расширяет.
RINGS = ("точечно", "вокруг", "вся школа")


def movable(doc: dict, lessons: list[dict], change: dict, ring: int) -> list[dict] | None:
    """Уроки, которые пересборке разрешено двигать. None — можно все.

    Круг 1: затронутые классы и учителя, которые в них ведут (иначе учитель
    не сможет подвинуться вслед за своим уроком). Круг 2: волна на шаг дальше —
    плюс другие классы этих учителей. Круг 3: вся школа.
    """
    if ring >= 2:
        return None
    classes = _touched_classes(doc, change)
    if not classes:
        return None
    school, _ = build_school(tables_from_dict(doc), doc.get("settings") or {}, doc.get("wishes"),
                             doc.get("targeted"))
    of_group = {g.id: set(g.class_ids) for g in school.groups}
    where = lambda l: of_group.get(l["group_id"], set())  # noqa: E731

    teachers = {l["teacher_id"] for l in lessons if where(l) & classes}
    if ring >= 1:
        classes = classes | {c for l in lessons if l["teacher_id"] in teachers for c in where(l)}
        teachers = teachers | {l["teacher_id"] for l in lessons if where(l) & classes}
    return [l for l in lessons if where(l) & classes or l["teacher_id"] in teachers]


def _touched_classes(doc: dict, change: dict) -> set[str]:
    """Каких классов касается изменение."""
    names = [str(c.get("класс", "")).strip() for c in doc["tables"].get("classes", [])]
    names = [n for n in names if n]
    aim = change.get("aim") or {}
    scope, who = aim.get("scope"), str(aim.get("who") or "").strip()
    if change.get("kind") != "aim" or scope == "school":
        return set()
    if scope == "class":
        return {who}
    if scope == "parallel":
        return {n for n in names if n.startswith(who)}
    if scope == "teacher":
        return {str(row.get("класс", "")).strip() for row in doc["tables"].get("load", [])
                if str(row.get("учитель", "")).strip() == who}
    if scope == "subject":
        return {str(row.get("класс", "")).strip() for row in doc["tables"].get("load", [])
                if str(row.get("предмет", "")).strip() == who}
    return set()


def _options(doc: dict, budget: float, hint: list[dict] | None) -> dict:
    settings = doc.get("settings") or {}
    return {
        "budget": budget,
        "preset": settings.get("preset") or "Поровну",
        "rules": settings.get("rules") or {},
        "prefs": settings.get("prefs") or {},
        "hint": hint,
        "keep": hint is not None,
        # Два солвера делят ядра поровну — иначе один отнимет время у другого,
        # и сравнение снова станет нечестным. Меньше четырёх потоков не даём:
        # CP-SAT держит в них разные стратегии (см. available_cpus).
        "params": {"num_workers": max(4, available_cpus() // 2)},
    }


def input_blockers(doc: dict) -> list[str]:
    """Проверка ввода для изменённой школы.

    Пожелание-число завуч может назвать невыполнимым: «у 9Г не больше шести
    уроков» при 32 уроках в неделю — это 30 мест на 32 урока. Проверка ввода
    это видит и называет причину, а без неё сравнение просто не посчиталось бы
    и экран остался бы пустым (найдено 22.09.2026).
    """
    _, problems = build_school(tables_from_dict(doc), doc.get("settings") or {},
                               doc.get("wishes"), doc.get("targeted"))
    return problems[:5]


def blockers(doc: dict, change: dict) -> list[str]:
    """Почему с изменением расписание не сложится — видно без солвера.

    Солвер на такой вопрос отвечает «решения нет» за секунду, но без причины,
    а завучу нужна причина. Найдено первым же прогоном 15.09.2026: у учителя
    математика по 5 часов, и выходной в любой день делает школу нерешаемой —
    без сдвоенных уроков 5 часов значит урок каждый день.
    """
    if change.get("kind") != "teacher_day_off":
        return []
    school, problems = build_school(tables_from_dict(doc), doc.get("settings") or {}, doc.get("wishes"))
    if problems:
        return []
    teacher = next((t for t in school.teachers if t.name == change.get("teacher")), None)
    if teacher is None:
        return []
    days = sorted(d for d, kind in school.day_kinds.items() if kind.value == "lessons")
    periods = range(1, school.periods_per_day + 1)
    free_days = [d for d in days if d != teacher.method_day
                 and not all(any(s.day == d and s.period == p for s in teacher.unavailable) for p in periods)]
    subjects = {s.id: s for s in school.subjects}
    parallels = {c.id: c.parallel for c in school.classes}
    names = {c.id: c.name for c in school.classes}
    rules = (doc.get("settings") or {}).get("rules") or {}
    found = []
    for item in school.load:
        if item.teacher_id != teacher.id:
            continue
        group = school.group(item.group_id)
        subject = subjects[item.subject_id]
        where = ", ".join(names.get(c, c) for c in group.class_ids)
        parallel = max((parallels.get(c, 0) for c in group.class_ids), default=0)
        double = school.norms.double_allowed(subject.name, parallel, item.level.value != "base") \
            or (subject.always_double and item.hours_per_week % 2 == 0)
        if item.hours_per_week > len(free_days) * (2 if double else 1):
            found.append(f"{subject.name} в {where}: {item.hours_per_week} ч в неделю, а у учителя остаётся "
                         f"{len(free_days)} учебных дня и не больше одного такого урока в день (п. 65 ССЭТ).")
        # Физкультура без соседних дней при 3 часах в пятидневку — только пн/ср/пт (п. 94).
        room = (len(days) + 1) // 2
        if school.norms.is_pe(subject.name) and rules.get("pe_two_days", "hard") == "hard" \
                and item.hours_per_week == room and len(days) % 2 == 1 and change.get("day") in days[::2]:
            found.append(f"{subject.name} в {where}: {item.hours_per_week} ч без двух дней подряд ставятся только "
                         f"в {', '.join(DAY_NAMES[d] for d in days[::2])} (п. 94 ССЭТ).")
    return found[:5]


class WhatIfRequest(BaseModel):
    change: dict
    mode: str = "keep"  # keep — беречь текущее расписание, fresh — составить с нуля
    ring: int = 0  # насколько широко ворошим сетку: 0 — точечно, 2 — вся школа


@router.post("")
def start(school_id: str, body: WhatIfRequest) -> dict:
    found = db.get_school(school_id)
    if not found:
        raise HTTPException(404, "Школа не найдена")
    doc, revision = found
    base = db.latest_schedule(school_id)
    if base is None:
        raise HTTPException(404, "Сначала составьте расписание: сравнивать не с чем")
    changed, label = apply_change(doc, body.change)
    blocked = input_blockers(changed) or blockers(changed, body.change)
    if blocked:  # считать нечего: ответ «нельзя» известен сразу, и с причиной
        return {"label": label, "blocked": blocked}
    mode = body.mode if body.mode in BUDGETS else "keep"
    hint = base["lessons"] if mode == "keep" else None
    pair = uuid.uuid4().hex[:12]
    # Чем шире круг, тем больше работы: точечной правке хватает минуты,
    # а «всю школу» за минуту успевает только испортить — на Жемчужненской
    # за 60 с переставлялся каждый четвёртый урок (замер 22.09.2026).
    budget = BUDGETS[mode] if mode != "keep" else (60, 90, 150)[max(0, min(2, body.ring))]

    # Круг правки. Закреплённые уроки — те, что вне круга; считает их система,
    # а не завуч пальцем. Круг одинаков для контроля и варианта, иначе
    # сравнение перестанет быть честным (CLAUDE.md §8.3).
    ring = max(0, min(2, body.ring))
    free = movable(doc, base["lessons"], body.change, ring) if mode == "keep" else None
    pinned = None
    if free is not None:
        keys = {(l["group_id"], l["subject_id"], l["day"], l["period"]) for l in free}
        pinned = [l for l in base["lessons"]
                  if (l["group_id"], l["subject_id"], l["day"], l["period"]) not in keys]

    jobs = {}
    for role, variant_doc in (("control", doc), ("variant", changed)):
        meta = {"change": body.change, "label": label, "role": role, "pair": pair,
                "mode": mode, "budget": budget, "base_id": base["id"],
                "ring": ring, "movable": len(free) if free is not None else None}

        def on_result(job, meta=meta) -> None:
            result = job.result or {}
            if result.get("type") == "result" and result.get("lessons"):
                job.schedule_id = db.save_schedule(
                    school_id, revision, result["lessons"],
                    {**meta, **{k: result.get(k) for k in ("status", "seconds", "relaxed")}})

        options = _options(variant_doc, budget, hint)
        if pinned is not None:
            options["pinned"] = pinned
        job = start_job(school_id, revision, variant_doc, options, on_result)
        jobs[role] = job.id
    return {"label": label, "budget": budget, "ring": ring,
            "ring_name": RINGS[ring],
            "movable": len(free) if free is not None else len(base["lessons"]),
            "total": len(base["lessons"]), **jobs}


def _side(school_id: str, doc: dict, row: dict, base_lessons: list[dict]) -> dict:
    school, problems = build_school(tables_from_dict(doc), doc.get("settings") or {}, doc.get("wishes"))
    if problems:
        raise HTTPException(422, {"problems": problems})
    lessons = lessons_from_dict(row["lessons"])
    report = check(school, lessons)
    return {
        "id": row["id"],
        "lessons": row["lessons"],
        "seconds": row["meta"].get("seconds"),
        "metrics": {
            "norms": len(report.norm_violations),
            "conflicts": len(report.structural_violations),
            "teacher_gaps": report.teacher_gaps,
            "teacher_days": report.teacher_days,
            "moved": _moved(base_lessons, row["lessons"]),
            **{k: v for k, v in measure(school, lessons).items() if k != "examples"},
        },
    }


def _moved(before: list[dict], after: list[dict]) -> int:
    """Сколько уроков стоят не там, где в текущем расписании."""
    from collections import Counter
    key = lambda l: (l["group_id"], l["subject_id"], l["teacher_id"], l["day"], l["period"])  # noqa: E731
    return sum((Counter(map(key, before)) - Counter(map(key, after))).values())


def _pair(school_id: str, control_id: str, variant_id: str) -> tuple[dict, dict]:
    control, variant = db.get_schedule(control_id), db.get_schedule(variant_id)
    if not control or not variant or control["school_id"] != school_id or variant["school_id"] != school_id \
            or control["meta"].get("pair") != variant["meta"].get("pair") \
            or variant["meta"].get("role") != "variant":
        raise HTTPException(404, "Сравнение не найдено")
    return control, variant


@router.get("")
def compare(school_id: str, control: str, variant: str) -> dict:
    found = db.get_school(school_id)
    if not found:
        raise HTTPException(404, "Школа не найдена")
    doc, revision = found
    control_row, variant_row = _pair(school_id, control, variant)
    meta = variant_row["meta"]
    base = db.get_schedule(meta["base_id"])
    base_lessons = base["lessons"] if base else []
    changed, label = apply_change(doc, meta["change"])
    return {
        "label": label,
        "change": meta["change"],
        "mode": meta["mode"],
        "budget": meta["budget"],
        "ring": meta.get("ring", 2),
        "ring_name": RINGS[min(2, meta.get("ring", 2))],
        # Данные школы поменялись после расчёта — принимать вариант уже нельзя:
        # его сетка составлена по прежним данным.
        "stale": variant_row["revision_id"] != revision,
        "control": _side(school_id, doc, control_row, base_lessons),
        "variant": _side(school_id, changed, variant_row, base_lessons),
    }


class ApplyRequest(BaseModel):
    control: str
    variant: str


@router.post("/apply")
def accept(school_id: str, body: ApplyRequest) -> dict:
    """Принять вариант: изменение уходит в данные школы, его сетка — в расписание."""
    found = db.get_school(school_id)
    if not found:
        raise HTTPException(404, "Школа не найдена")
    doc, revision = found
    _, variant = _pair(school_id, body.control, body.variant)
    if variant["revision_id"] != revision:
        raise HTTPException(409, "Данные школы изменились после расчёта — посчитайте вариант заново")
    changed, label = apply_change(doc, variant["meta"]["change"])
    new_revision = db.save_school(school_id, changed)
    schedule_id = db.save_schedule(school_id, new_revision, variant["lessons"],
                                   {"status": variant["meta"].get("status"),
                                    "seconds": variant["meta"].get("seconds"),
                                    "relaxed": variant["meta"].get("relaxed"),
                                    "accepted": label})
    return {"schedule_id": schedule_id, "label": label}
