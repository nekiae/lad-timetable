"""Все данные, из которых собрано расписание, — одним PDF на проверку.

    .venv/bin/python tools/input_pdf.py <id школы> out/dannye.pdf

Расписание спорить не о чем, пока не сверены входные данные: если мы неверно
прочитали комплектование, неверным будет и всё остальное. Поэтому здесь ровно
то, что система держит у себя: классы со сменами и кабинетами, кабинетный фонд,
нагрузка по классам и итог часов по учителям. Завуч сверяет это со своей
тарификацией — и половина будущих «а почему так?» отпадает.

Отдельным разделом — места, где мы прочитали документ не буквально: что
исправили и почему. Их скрывать нельзя: это наши решения за школу.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

from fpdf import FPDF

ROOT = Path(__file__).resolve().parents[1]
FONTS = ROOT / "data" / "fonts"
BASE = "http://127.0.0.1:8000"

INK = (23, 32, 56)
PENCIL = (106, 116, 140)
RULE = (214, 220, 232)
BAND = (244, 246, 250)

LEAD = ("Ниже — всё, что система знает о школе: из этого и собрано расписание. "
        "Данные взяты из вашего комплектования на 2026/27 и из таблицы классов "
        "с кабинетами и сменами. Если где-то мы прочитали неверно, расписание "
        "тоже будет неверным — поэтому сверьте, пожалуйста, глазами.")

# Как мы прочитали документ не буквально. Список ведётся вручную и повторяет
# LINE_FIX и ASSUMED из tools/import_zhemchuzhny.py: это решения, принятые
# за школу, и она должна их увидеть.
READINGS = [
    ("«8д» читаем как 9«Д»", "Вы сказали, что восьмых классов четыре, а комплектование "
     "верстали поверх прошлогоднего. Все одиночные «8д» отнесли к 9«Д»."),
    ("«8абвгд – 5 ч.» у информатики — это 8абвг по часу",
     "Пятая литера осталась с прошлого года: восьмых классов четыре."),
    ("«9 абвг – 5 ч.» у информатики — это 9абвгд",
     "Пять часов на четыре класса не делится, а девятых классов пять."),
    ("Биология у Хоровец Г. Г. — восьмые классы, а не девятые",
     "Ваш ответ: «У Хоровец только седьмые и восьмые»."),
    ("«10, 11аб – 3 ч.» у допризывной — по часу каждому из трёх классов", ""),
    ("Русский в 7«Б», 7«В», 7«Г» — 4 часа, а не 5",
     "Это наше предположение, оно в листе вопросов первым пунктом."),
    ("Дроби «3/4 ч.» — первое и второе полугодие", "Берём первое: расписание "
     "составляется на полугодие."),
    ("«Язык и литература» одной строкой разложены по типовому плану № 75",
     "«5а – 5 ч.» у словесника — это 3 часа языка и 2 литературы."),
    ("Повторы одного предмета в классе у разных учителей отброшены",
     "Белорусский в десятом был записан трижды по три часа; оставили первого "
     "по документу. Кто ведёт на самом деле — вопрос к вам."),
    ("Начальная школа не бралась", "Часы английского в 3–4 классах в расписание "
     "не вошли: у началки своё."),
]


class Sheet(FPDF):
    def header(self) -> None:
        if self.page_no() == 1:
            return
        self.set_font("Plex", "", 8)
        self.set_text_color(*PENCIL)
        self.set_y(10)
        self.cell(0, 5, "Данные, из которых собрано расписание", align="L")
        self.ln(5)

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("Plex", "", 8)
        self.set_text_color(*PENCIL)
        self.cell(0, 5, "ЛАД · Владислав Неки · сентябрь 2026", align="L")
        self.cell(0, 5, str(self.page_no()), align="R")

    def heading(self, text: str, note: str = "") -> None:
        if self.get_y() > self.h - 40:
            self.add_page()
        self.ln(3)
        self.set_font("Plex", "B", 12)
        self.set_text_color(*INK)
        self.multi_cell(0, 6, text, align="L")
        if note:
            self.set_font("Plex", "", 9)
            self.set_text_color(*PENCIL)
            # multi_cell оставляет курсор справа от текста — возвращаем к полю,
            # иначе ширина следующего блока схлопывается в ноль.
            self.set_x(self.l_margin)
            self.multi_cell(0, 4.4, note, align="L")
        self.ln(1.5)

    def row(self, cells: list[tuple[str, float]], bold=False, color=INK, band=False) -> None:
        if self.get_y() > self.h - 20:
            self.add_page()
        self.set_font("Plex", "B" if bold else "", 8.6)
        self.set_text_color(*color)
        if band:
            self.set_fill_color(*BAND)
        for text, width in cells:
            self.cell(width, 4.8, text, fill=band)
        self.ln(4.8)


def fetch(path: str) -> dict:
    with urllib.request.urlopen(f"{BASE}{path}") as r:
        return json.load(r)


def build(school: str, out: Path) -> Path:
    doc = fetch(f"/api/schools/{school}")["doc"]
    tables = doc["tables"]
    settings = doc.get("settings") or {}

    pdf = Sheet(format="A4")
    pdf.set_auto_page_break(True, margin=16)
    pdf.add_font("Plex", "", FONTS / "IBMPlexSans-Regular.ttf")
    pdf.add_font("Plex", "B", FONTS / "IBMPlexSans-SemiBold.ttf")
    pdf.set_margins(15, 14, 15)
    pdf.add_page()

    pdf.set_font("Plex", "B", 15)
    pdf.set_text_color(*INK)
    pdf.multi_cell(0, 7, f"Данные, из которых собрано расписание\n{settings.get('name', '')}",
                   align="L")
    pdf.ln(2)
    pdf.set_font("Plex", "", 9.5)
    pdf.set_text_color(*PENCIL)
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(0, 4.6, LEAD, align="L")
    pdf.ln(2)

    load = tables.get("load", [])
    classes = tables.get("classes", [])
    second = int(settings.get("вторая смена с урока") or 0)
    per_second = int(settings.get("уроков во второй смене") or 0)

    pdf.heading("Режим школы")
    pdf.row([(f"Учебных дней в неделю: {settings.get('days', 5)}", 58),
             (f"Уроков в первой смене: {settings.get('periods', 8)}", 60),
             (f"Вторая смена: с {second}-го урока, {per_second} уроков", 60)])
    pdf.row([(f"Классов: {len(classes)}", 58),
             (f"Учителей: {len(tables.get('teachers', []))}", 60),
             (f"Строк нагрузки: {len(load)}", 60)])

    pdf.heading("Классы", "Смена и кабинет — из вашей таблицы классных руководителей.")
    pdf.row([("Класс", 20), ("Смена", 18), ("Кабинет", 22), ("Учеников", 22),
             ("Класс", 20), ("Смена", 18), ("Кабинет", 22), ("Учеников", 22)],
            bold=True, band=True)
    rows = [(str(c.get("класс")), str(c.get("смена", "1")), str(c.get("кабинет", "—")),
             str(c.get("учеников", ""))) for c in classes]
    for left, right in zip(rows[::2], rows[1::2] + [("", "", "", "")]):
        pdf.row([(left[0], 20), (left[1], 18), (left[2], 22), (left[3], 22),
                 (right[0], 20), (right[1], 18), (right[2], 22), (right[3], 22)])

    pdf.heading("Кабинеты")
    pdf.row([("Кабинет", 26), ("Тип", 62), ("Мест", 18), ("Классов сразу", 30)],
            bold=True, band=True)
    for room in tables.get("rooms", []):
        pdf.row([(str(room.get("кабинет")), 26), (str(room.get("тип")), 62),
                 (str(room.get("мест", "")), 18), (str(room.get("классов сразу", 1)), 30)])

    pdf.heading("Нагрузка по классам",
                "Столько часов система обязана выдать. «Группа» — деление класса; "
                "две группы одного предмета идут одновременно.")
    by_class: dict[str, list[dict]] = defaultdict(list)
    for item in load:
        by_class[str(item.get("класс"))].append(item)
    order = sorted(by_class, key=lambda n: (int("".join(c for c in n if c.isdigit()) or 0), n))
    for name in order:
        items = by_class[name]
        whole = sum(int(i.get("часов") or 0) for i in items if not str(i.get("подгруппа") or ""))
        by_subject: dict[str, int] = {}
        for i in items:
            if str(i.get("подгруппа") or ""):
                key = str(i.get("предмет"))
                by_subject[key] = max(by_subject.get(key, 0), int(i.get("часов") or 0))
        pdf.ln(1.5)
        pdf.row([(f"{name} — {whole + sum(by_subject.values())} уроков в неделю", 136)],
                bold=True)
        pdf.row([("Предмет", 52), ("Часов", 14), ("Учитель", 48), ("Группа", 22)],
                bold=True, color=PENCIL)
        for i in sorted(items, key=lambda x: (str(x.get("предмет")), str(x.get("подгруппа")))):
            level = "" if str(i.get("уровень")) == "базовый" else " (повыш.)"
            pdf.row([(str(i.get("предмет")) + level, 52), (str(i.get("часов")), 14),
                     (str(i.get("учитель")), 48), (str(i.get("подгруппа") or "весь класс"), 22)])

    pdf.add_page()
    pdf.heading("Часы по учителям",
                "Сверьте с тарификацией: столько часов система отдала каждому.")
    by_teacher: dict[str, int] = defaultdict(int)
    for item in load:
        by_teacher[str(item.get("учитель"))] += int(item.get("часов") or 0)
    names = sorted(by_teacher)
    pdf.row([("Учитель", 62), ("Часов", 16), ("Учитель", 62), ("Часов", 16)],
            bold=True, band=True)
    for left, right in zip(names[::2], names[1::2] + [""]):
        pdf.row([(left, 62), (str(by_teacher[left]), 16),
                 (right, 62), (str(by_teacher.get(right, "")), 16)])

    pdf.heading("Где мы прочитали документ не буквально",
                "Это решения, принятые за школу. Если хоть одно неверно — скажите, "
                "пересоберём.")
    for title, why in READINGS:
        pdf.set_font("Plex", "B", 9)
        pdf.set_text_color(*INK)
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(0, 4.4, f"— {title}", align="L")
        if why:
            pdf.set_font("Plex", "", 9)
            pdf.set_text_color(*PENCIL)
            pdf.set_x(pdf.l_margin + 4)
            pdf.multi_cell(pdf.w - pdf.l_margin * 2 - 4, 4.2, why, align="L")
        pdf.ln(1.2)

    out.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(out))
    return out


if __name__ == "__main__":
    school = sys.argv[1] if len(sys.argv) > 1 else "3e8bc4817797"
    target = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "out" / "dannye.pdf"
    print("готово:", build(school, target))
