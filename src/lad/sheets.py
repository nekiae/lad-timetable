"""Листы на выдачу файлом: PDF и Excel.

Печать из браузера годится, пока завуч стоит у принтера. Но лист замен утром
чаще отправляют в чат учителей, а расписание класса — классному руководителю.
Для этого нужен файл, а не диалог печати с «Сохранить как PDF», который в каждом
браузере спрятан по-своему.

PDF собирается здесь, на сервере: fpdf2 и IBM Plex Sans из data/fonts (тот же
шрифт, что в интерфейсе, и в нём есть кириллица). Модуль ничего не знает про
анонимизацию и даты: подписи приходят готовыми, чтобы файл совпадал с тем, что
завуч видит на экране.
"""

from __future__ import annotations

from collections import defaultdict
from io import BytesIO
from pathlib import Path

from fpdf import FPDF
from fpdf.fonts import FontFace
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, Side

from .model import Lesson, School

FONTS = Path(__file__).resolve().parents[2] / "data" / "fonts"
INK = (28, 43, 79)
PENCIL = (95, 106, 132)
RULE = (221, 228, 239)
PAPER = (246, 248, 251)
DAY_NAMES = {1: "Понедельник", 2: "Вторник", 3: "Среда", 4: "Четверг", 5: "Пятница", 6: "Суббота"}


def _pdf(orientation: str) -> FPDF:
    pdf = FPDF(orientation=orientation, format="A4", unit="mm")
    pdf.set_margins(12, 12, 12)
    pdf.set_auto_page_break(True, margin=12)
    pdf.add_font("Plex", "", FONTS / "IBMPlexSans-Regular.ttf")
    pdf.add_font("Plex", "B", FONTS / "IBMPlexSans-SemiBold.ttf")
    pdf.set_text_color(*INK)
    pdf.set_draw_color(*RULE)
    return pdf


def _plain(text: str) -> str:
    """Текст для ячейки с разметкой: **, __ и -- в fpdf2 — жирный, курсив, подчёркивание."""
    return text.replace("**", "*").replace("__", "_").replace("--", "–")


# ---------------------------------------------------------------- лист замен

def substitutions_pdf(title: str, subtitle: str, rows: list[list[str]]) -> bytes:
    pdf = _pdf("portrait")
    pdf.add_page()
    pdf.set_font("Plex", "B", 16)
    pdf.multi_cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Plex", "", 10)
    pdf.set_text_color(*PENCIL)
    pdf.multi_cell(0, 5, subtitle, new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(*INK)
    pdf.ln(5)
    pdf.set_font("Plex", "", 11)
    with pdf.table(col_widths=(14, 20, 62, 22, 68), line_height=7, padding=(1.5, 2),
                   borders_layout="HORIZONTAL_LINES", headings_style=FontFace(emphasis="BOLD")) as table:
        for row in [["Урок", "Класс", "Предмет", "Кабинет", "Заменяет"], *rows]:
            line = table.row()
            for value in row:
                line.cell(str(value))
    pdf.ln(16)
    pdf.set_font("Plex", "", 10)
    pdf.set_text_color(*PENCIL)
    pdf.cell(0, 6, "Заместитель директора  ______________________")
    return bytes(pdf.output())


def substitutions_xlsx(title: str, subtitle: str, rows: list[list[str]]) -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.title = "Замены"
    sheet["A1"] = title
    sheet["A1"].font = Font(bold=True, size=14)
    sheet["A2"] = subtitle
    sheet["A2"].font = Font(color="5F6A84")
    line = Side(style="thin", color="BFBFBF")
    for c, head in enumerate(["Урок", "Класс", "Предмет", "Кабинет", "Заменяет"], start=1):
        cell = sheet.cell(row=4, column=c, value=head)
        cell.font = Font(bold=True)
        cell.border = Border(bottom=Side(style="medium", color="1C2B4F"))
    for r, row in enumerate(rows, start=5):
        for c, value in enumerate(row, start=1):
            cell = sheet.cell(row=r, column=c, value=int(value) if c == 1 and str(value).isdigit() else value)
            cell.border = Border(bottom=line)
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    for letter, width in zip("ABCDE", (7, 9, 32, 10, 30)):
        sheet.column_dimensions[letter].width = width
    sheet.page_setup.orientation = "portrait"
    sheet.page_setup.fitToWidth = 1
    out = BytesIO()
    book.save(out)
    return out.getvalue()


# ---------------------------------------------------------------- листы расписания

def timetable_sheets(school: School, lessons: list[Lesson], by: str, anonymize: bool) -> list[dict]:
    """Листы A4 как на странице печати: по классам или по учителям.

    Клетка — список записей (жирная строка, серая строка). Подгруппы одного
    предмета — одной записью, учителя через косую: иначе клетка с делением
    занимает четыре строки и лист не влезает на страницу.
    """
    subjects = {s.id: s.name for s in school.subjects}
    class_names = {c.id: c.name for c in school.classes}
    order = {t.id: n for n, t in enumerate(school.teachers, start=1)}
    names = {t.id: (f"Учитель {order[t.id]}" if anonymize else t.name) for t in school.teachers}
    surname = (lambda tid: names[tid]) if anonymize else (lambda tid: names.get(tid, tid).split(" ")[0])

    def cells(chosen: list[Lesson]) -> dict:
        grouped: dict[tuple, dict[str, list[Lesson]]] = defaultdict(lambda: defaultdict(list))
        for lesson in chosen:
            grouped[lesson.slot.day, lesson.slot.period][lesson.subject_id].append(lesson)
        result = {}
        for place, by_subject in grouped.items():
            entries = []
            for subject_id, items in by_subject.items():
                rooms = ", ".join(dict.fromkeys(l.room_id for l in items if l.room_id))
                room = f", каб. {rooms}" if rooms else ""
                if by == "teacher":
                    group = school.group(items[0].group_id)
                    part = f" ({group.part})" if group.part else ""
                    entries.append((", ".join(class_names.get(c, c) for c in group.class_ids) + part,
                                    subjects.get(subject_id, "") + room))
                else:
                    entries.append((subjects.get(subject_id, ""),
                                    " / ".join(surname(l.teacher_id) for l in items) + room))
            result[place] = entries
        return result

    if by == "teacher":
        ordered = sorted(school.teachers, key=lambda t: names[t.id])
        sheets = [{"title": names[t.id], "cells": cells([l for l in lessons if l.teacher_id == t.id])}
                  for t in ordered]
        return [s for s in sheets if s["cells"]]
    return [{"title": c.name,
             "cells": cells([l for l in lessons if c.id in school.group(l.group_id).class_ids])}
            for c in school.classes]


def timetable_pdf(school: School, sheets: list[dict]) -> bytes:
    days = sorted(d for d, kind in school.day_kinds.items() if kind.value == "lessons")
    periods = range(1, school.periods_per_day + 1)
    pdf = _pdf("landscape")
    width = pdf.epw
    day_width = (width - 10) / len(days)
    for sheet in sheets:
        pdf.add_page()
        pdf.set_font("Plex", "B", 20)
        pdf.cell(width / 2, 10, sheet["title"])
        pdf.set_font("Plex", "", 9)
        pdf.set_text_color(*PENCIL)
        pdf.cell(width / 2, 10, school.name, align="R", new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(*INK)
        pdf.set_draw_color(*INK)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + width, pdf.get_y())
        pdf.set_draw_color(*RULE)
        pdf.ln(2)
        pdf.set_font("Plex", "", 8.5)
        with pdf.table(col_widths=(10, *[day_width] * len(days)), line_height=3.9, padding=(1.2, 1.5),
                       markdown=True, borders_layout="INTERNAL", text_align="LEFT",
                       headings_style=FontFace(emphasis="BOLD", fill_color=PAPER)) as table:
            head = table.row()
            head.cell("")
            for day in days:
                head.cell(DAY_NAMES[day])
            for period in periods:
                row = table.row()
                row.cell(str(period))
                for day in days:
                    entries = sheet["cells"].get((day, period), [])
                    text = "\n".join(f"**{_plain(top)}**\n{_plain(bottom)}" for top, bottom in entries)
                    row.cell(text or "\n\n")
    return bytes(pdf.output())
