"""Импорт чужой таблицы нагрузки: разобрать файл → предпросмотр → положить в данные.

Файл ходит между шагами целиком (base64 в теле запроса), а не хранится на
сервере: так нет ни временных файлов, ни «загрузил, ушёл, файл завис».
Тарификационный список школы — десятки килобайт.
"""

from __future__ import annotations

import base64

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from .entry import _open, _save

from lad.tarif_import import apply, extract, inspect, read_book  # noqa: E402

router = APIRouter(prefix="/api/schools/{school_id}/tarif")


@router.post("/inspect")
async def inspect_file(school_id: str, request: Request) -> dict:
    """Листы файла, первые строки и догадка: где заголовки и какая колонка что значит."""
    _open(school_id)
    try:
        return inspect(await request.body())
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


class TarifBody(BaseModel):
    file: str  # base64 .xlsx
    sheet: str
    header_row: int  # номер строки заголовков с нуля
    layout: str = "long"  # long — строка на урок, wide — учитель × классы
    mapping: dict[str, int | None] = {}
    class_columns: list[int] = []
    fill_down: bool = True
    shorten: bool = True
    mode: str = "replace"  # replace — заменить нагрузку, add — добавить


def _extract(school_id: str, body: TarifBody):
    doc, tables = _open(school_id)
    try:
        rows = read_book(base64.b64decode(body.file)).get(body.sheet)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    if rows is None:
        raise HTTPException(422, f"В файле нет листа «{body.sheet}»")
    known = [str(n).strip() for n in tables["subjects"].get("предмет", []) if str(n).strip()]
    result = extract(rows, body.header_row, "wide" if body.layout == "wide" else "long", body.mapping,
                     body.class_columns, body.fill_down, body.shorten, known)
    return doc, tables, result


@router.post("/preview")
def preview(school_id: str, body: TarifBody) -> dict:
    _, tables, result = _extract(school_id, body)
    records = result.pop("records")
    _, created = apply(tables, records, "add" if body.mode == "add" else "replace")
    return {**result, "rows": records[:40], "total": len(records), "hours": sum(r["часов"] for r in records),
            "skipped": result["skipped"][:40], "skipped_total": len(result["skipped"]),
            "new": {k: created[k] for k in ("classes", "subjects", "teachers")}, "load_rows": created["load_rows"]}


@router.post("/apply")
def apply_file(school_id: str, body: TarifBody) -> dict:
    doc, tables, result = _extract(school_id, body)
    if not result["records"]:
        raise HTTPException(422, "Из файла не получилось ни одной строки нагрузки — проверьте, какие колонки выбраны")
    tables, created = apply(tables, result["records"], "add" if body.mode == "add" else "replace")
    return _save(school_id, doc, tables, tarif={"rows": len(result["records"]), **created,
                                                "skipped_total": len(result["skipped"]), "split": result["split"]})
