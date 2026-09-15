"""Листы файлом: лист замен (PDF, Excel) и листы расписания (PDF).

Лист замен собирает браузер — с выбранными заменами, датой и скрытыми ФИО,
если завуч их скрыл, — а сервер только превращает его в файл. Листы расписания
сервер собирает сам из последней сохранённой версии, как страница печати.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from . import db

from lad.sheets import substitutions_pdf, substitutions_xlsx, timetable_pdf, timetable_sheets  # noqa: E402
from lad.storage import lessons_from_dict  # noqa: E402
from lad.tables import build_school, tables_from_dict  # noqa: E402

router = APIRouter(prefix="/api/schools/{school_id}")

PDF = "application/pdf"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class SheetBody(BaseModel):
    title: str
    subtitle: str = ""
    rows: list[list[str]]


def _file(data: bytes, media: str, name: str) -> Response:
    return Response(data, media_type=media, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.post("/substitutions/sheet.pdf")
def substitutions_sheet_pdf(school_id: str, body: SheetBody) -> Response:
    return _file(substitutions_pdf(body.title, body.subtitle, body.rows), PDF, "zameny.pdf")


@router.post("/substitutions/sheet.xlsx")
def substitutions_sheet_xlsx(school_id: str, body: SheetBody) -> Response:
    return _file(substitutions_xlsx(body.title, body.subtitle, body.rows), XLSX, "zameny.xlsx")


@router.get("/print.pdf")
def print_pdf(school_id: str, by: str = "class", anonymize: bool = False) -> Response:
    found = db.get_school(school_id)
    if not found:
        raise HTTPException(404, "Школа не найдена")
    doc, _ = found
    school, problems = build_school(tables_from_dict(doc), doc.get("settings") or {}, doc.get("wishes"))
    if problems:
        raise HTTPException(422, {"problems": problems})
    row = db.latest_schedule(school_id)
    if row is None:
        raise HTTPException(404, "Расписания ещё нет")
    by = "teacher" if by == "teacher" else "class"
    sheets = timetable_sheets(school, lessons_from_dict(row["lessons"]), by, anonymize)
    return _file(timetable_pdf(school, sheets), PDF, f"raspisanie-{by}.pdf")
