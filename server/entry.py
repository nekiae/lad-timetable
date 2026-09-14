"""Ввод данных школы: быстрые действия поверх `lad.tables`.

Логика ввода уже написана и проверена на Streamlit — генерация классов
по параллелям, предметы и черновик нагрузки из типового плана, назначение
учителей по предмету, раздача классов поровну. Здесь она только выставлена
наружу HTTP-ручками. Переписывать её на фронте нельзя: у каждой функции
в комментариях найденные на живых данных ловушки, и вторая копия их потеряет.

Каждое действие сохраняет школу новой ревизией и возвращает документ целиком,
чтобы интерфейс не собирал его заново по кусочкам.
"""

from __future__ import annotations

import json

import pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import db

from lad.tables import (  # noqa: E402
    LESSON_KINDS, LEVELS, ROOM_KINDS, add_subject_slots, assign_teacher, generate_classes,
    generate_load, generate_rooms, generate_subjects, input_status, next_step, parallels_of,
    rooms_verdict, slot_label, spread_evenly, split_subjects, tables_from_dict, teacher_hours,
)

router = APIRouter(prefix="/api/schools/{school_id}")


def _open(school_id: str) -> tuple[dict, dict[str, pd.DataFrame]]:
    found = db.get_school(school_id)
    if not found:
        raise HTTPException(404, "Школа не найдена")
    doc, _ = found
    return doc, tables_from_dict(doc)


def _records(table: pd.DataFrame) -> list[dict]:
    # Через JSON, а не to_dict: numpy-числа и NaN иначе не сериализуются.
    return json.loads(table.to_json(orient="records", force_ascii=False))


def _save(school_id: str, doc: dict, tables: dict[str, pd.DataFrame], **extra) -> dict:
    doc["tables"] = {name: _records(table) for name, table in tables.items()}
    revision = db.save_school(school_id, doc)
    return {"doc": doc, "revision": revision, **extra}


@router.get("/input")
def input_state(school_id: str) -> dict:
    """Что введено, что делать дальше и чем заполнять выпадающие списки."""
    doc, tables = _open(school_id)
    status = input_status(tables, doc.get("wishes"))
    todo = next_step(status)
    return {
        "steps": status,
        "next": todo["key"] if todo else None,
        "rooms_verdict": rooms_verdict(tables),
        "divided": sorted(split_subjects(tables["load"])),
        "teacher_hours": teacher_hours(tables["load"]),
        "options": {"room_kinds": list(ROOM_KINDS), "levels": list(LEVELS),
                    "lesson_kinds": list(LESSON_KINDS)},
    }


class ClassCounts(BaseModel):
    counts: dict[int, int]
    sizes: dict[int, int] = {}


@router.post("/classes/generate")
def classes_generate(school_id: str, body: ClassCounts) -> dict:
    doc, tables = _open(school_id)
    if len(tables["classes"]):
        raise HTTPException(409, "Классы уже заведены — правьте их в таблице")
    tables["classes"] = generate_classes({p: n for p, n in body.counts.items() if n}, body.sizes)
    return _save(school_id, doc, tables, added=len(tables["classes"]))


class RoomCounts(BaseModel):
    regular: int
    special: dict[str, int] = {}


@router.post("/rooms/generate")
def rooms_generate(school_id: str, body: RoomCounts) -> dict:
    doc, tables = _open(school_id)
    if len(tables["rooms"]):
        raise HTTPException(409, "Кабинеты уже заведены — правьте их в таблице")
    tables["rooms"] = generate_rooms(body.regular, {k: v for k, v in body.special.items() if v})
    return _save(school_id, doc, tables, added=len(tables["rooms"]))


@router.post("/subjects/from-plan")
def subjects_from_plan(school_id: str) -> dict:
    doc, tables = _open(school_id)
    suggested = generate_subjects(parallels_of(tables["classes"]))
    have = set(tables["subjects"]["предмет"].astype(str))
    add = suggested[~suggested["предмет"].isin(have)]
    if len(add):
        tables["subjects"] = pd.concat([tables["subjects"], add], ignore_index=True)
    return _save(school_id, doc, tables, added=len(add))


@router.post("/load/from-plan")
def load_from_plan(school_id: str) -> dict:
    """Недостающие строки нагрузки по типовому плану, без учителей."""
    doc, tables = _open(school_id)
    draft, unknown = generate_load(tables["classes"])
    existing = {(str(r["класс"]), str(r["предмет"]), str(r.get("подгруппа") or ""))
                for _, r in tables["load"].iterrows()}
    add = [r for _, r in draft.iterrows()
           if (str(r["класс"]), str(r["предмет"]), str(r["подгруппа"])) not in existing]
    if add:
        tables["load"] = pd.concat([tables["load"], pd.DataFrame(add)], ignore_index=True)
    return _save(school_id, doc, tables, added=len(add), unknown=unknown)


class Assign(BaseModel):
    subject: str
    teacher: str
    classes: list[str]  # «5А» или «5А (1)»; класс без строки нагрузки заводится
    previous: str | None = None  # прежний учитель этой строки, если его сменили
    hours: int | None = None  # часы для новых классов, если план их не задаёт


@router.post("/load/assign")
def load_assign(school_id: str, body: Assign) -> dict:
    """Закрепить за учителем ровно эти классы по предмету (см. assign_teacher)."""
    doc, tables = _open(school_id)
    load = tables["load"]
    divided = body.subject in split_subjects(load)
    known = {slot_label(r.get("класс"), r.get("подгруппа"))
             for _, r in load.iterrows() if str(r.get("предмет")) == body.subject}
    fresh = [c for c in body.classes if c not in known and " (" not in c]
    skipped: list[str] = []
    if fresh:
        load, skipped = add_subject_slots(load, body.subject, fresh, hours=body.hours)
    labels = [c for c in body.classes if c in known]
    for class_name in fresh:
        if class_name not in skipped:
            labels += [slot_label(class_name, part) for part in (("1", "2") if divided else ("",))]
    if body.previous and body.previous != body.teacher:
        load = assign_teacher(load, body.subject, body.previous, [])
    tables["load"] = assign_teacher(load, body.subject, body.teacher, labels)
    return _save(school_id, doc, tables, skipped=skipped)


class Spread(BaseModel):
    subject: str
    teachers: list[str]


@router.post("/load/spread")
def load_spread(school_id: str, body: Spread) -> dict:
    """Раздать свободные классы предмета поровну по часам (черновик за завуча)."""
    doc, tables = _open(school_id)
    tables["load"] = spread_evenly(tables["load"], body.subject, body.teachers)
    return _save(school_id, doc, tables)
