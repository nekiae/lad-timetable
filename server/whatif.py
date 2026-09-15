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

    raise HTTPException(422, "Неизвестное изменение")


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
    blocked = blockers(changed, body.change)
    if blocked:  # считать нечего: ответ «нельзя» известен сразу, и с причиной
        return {"label": label, "blocked": blocked}
    mode = body.mode if body.mode in BUDGETS else "keep"
    hint = base["lessons"] if mode == "keep" else None
    pair = uuid.uuid4().hex[:12]

    jobs = {}
    for role, variant_doc in (("control", doc), ("variant", changed)):
        meta = {"change": body.change, "label": label, "role": role, "pair": pair,
                "mode": mode, "budget": BUDGETS[mode], "base_id": base["id"]}

        def on_result(job, meta=meta) -> None:
            result = job.result or {}
            if result.get("type") == "result" and result.get("lessons"):
                job.schedule_id = db.save_schedule(
                    school_id, revision, result["lessons"],
                    {**meta, **{k: result.get(k) for k in ("status", "seconds", "relaxed")}})

        job = start_job(school_id, revision, variant_doc, _options(variant_doc, BUDGETS[mode], hint), on_result)
        jobs[role] = job.id
    return {"label": label, "budget": BUDGETS[mode], **jobs}


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
