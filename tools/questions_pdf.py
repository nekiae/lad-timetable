"""Лист вопросов к готовому расписанию — то, что уходит завучу вместе с сеткой.

    .venv/bin/python tools/questions_pdf.py <id школы> out/вопросы.pdf

Расписание без вопросов выглядит как утверждение: «вот, мы посчитали». А оно
посчитано из данных школы, и там, где данные спорные, спорным будет и результат.
Поэтому рядом с сеткой идёт лист: что мы поняли именно так, чего система
не знала и какие цифры не сошлись. Завуч отвечает на него один раз, и половина
замечаний к расписанию снимается ещё до разговора.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

from fpdf import FPDF

ROOT = Path(__file__).resolve().parents[1]
FONTS = ROOT / "data" / "fonts"
BASE = "http://127.0.0.1:8000"

INK = (23, 32, 56)
PENCIL = (106, 116, 140)
PEN = (37, 66, 158)
RULE = (214, 220, 232)

LEAD = ("Расписание на этом листе собрано из вашего комплектования на 2026/27. "
        "Всё, что в нём есть, взято оттуда; ничего мы не досочиняли. Но в нескольких "
        "местах данные можно прочитать двояко, а кое-чего система просто не знала. "
        "Ниже — ровно эти места. Отвечать можно коротко, хоть голосом, по номерам.")

ASSUMED = [
    ("Русский язык в 7«Б», 7«В», 7«Г» — 4 часа или 5?",
     "В комплектовании у Леончук Е. А. стоит «7бвг – 15 ч.», это по 5 часов на класс. "
     "У 7«А» русский ведёт Воробей Л. М., там «7а – 4/3 ч.» — 4 часа. Мы прочитали как 4: "
     "при пяти класс не помещается во вторую смену из шести уроков. Так верно?"),
]

NOT_KNOWN = [
    ("Начальную школу не ставили", "1–4 классы у вас со своими учителями, кабинетами "
     "и расписанием. Но английский в третьих и четвёртых ведут те же семь предметников, "
     "что и в старших: Сак, Качура, Ковригин, Калько, Рагинина, Сухомлинова, Яремчук. "
     "Система считает эти часы свободными и могла поставить им урок в то же время. "
     "Если пришлёте, когда они заняты в началке, — пересоберём без накладок."),
    ("Методические дни и совместительство", "Мы их не знаем: в комплектовании их нет. "
     "Если у кого-то есть день, когда его в школе быть не должно, — скажите, учтём."),
    ("Классные и информационные часы, факультативы", "В расписании их нет. "
     "Они занимают учителя и кабинет, поэтому их тоже стоит внести."),
]

CHECK = [
    "Можно ли это расписание поставить в работу? Если нет — что сломается первым?",
    "Что здесь неправильно с точки зрения школы, чего алгоритм знать не мог?",
    "Сколько дней ушло у вас на расписание в этом году?",
    "Что больнее — собрать в августе или разруливать замены каждый день?",
]


class Sheet(FPDF):
    def header(self) -> None:
        if self.page_no() == 1:
            return
        self.set_font("Plex", "", 8)
        self.set_text_color(*PENCIL)
        self.set_y(10)
        self.cell(0, 5, "Вопросы к расписанию", align="L")
        self.ln(6)

    def footer(self) -> None:
        self.set_y(-14)
        self.set_font("Plex", "", 8)
        self.set_text_color(*PENCIL)
        self.cell(0, 5, "ЛАД · Владислав Неки · сентябрь 2026", align="L")
        self.cell(0, 5, str(self.page_no()), align="R")

    def heading(self, text: str) -> None:
        self.ln(2)
        self.set_font("Plex", "B", 12)
        self.set_text_color(*INK)
        self.multi_cell(0, 6, text, align="L")
        self.ln(2)

    def body(self, text: str, color=INK, size=9.5) -> None:
        self.set_font("Plex", "", size)
        self.set_text_color(*color)
        self.multi_cell(0, 4.6, text, align="L")
        self.ln(1.4)

    def numbered(self, n: int, title: str, text: str = "") -> None:
        self.set_font("Plex", "B", 9.5)
        self.set_text_color(*INK)
        left = self.l_margin
        self.set_x(left)
        self.cell(6, 4.6, f"{n}.")
        self.multi_cell(self.w - left * 2 - 6, 4.6, title, align="L")
        if text:
            self.set_x(left + 6)
            self.set_font("Plex", "", 9.5)
            self.set_text_color(*PENCIL)
            self.multi_cell(self.w - left * 2 - 6, 4.4, text, align="L")
        self.ln(2)


def fetch(school: str) -> dict:
    with urllib.request.urlopen(f"{BASE}/api/schools/{school}/check") as r:
        return json.load(r)


def build(school: str, out: Path) -> Path:
    data = fetch(school)
    pdf = Sheet(format="A4")
    pdf.set_auto_page_break(True, margin=18)
    pdf.add_font("Plex", "", FONTS / "IBMPlexSans-Regular.ttf")
    pdf.add_font("Plex", "B", FONTS / "IBMPlexSans-SemiBold.ttf")
    pdf.set_margins(18, 16, 18)
    pdf.add_page()

    pdf.set_font("Plex", "B", 16)
    pdf.set_text_color(*INK)
    pdf.multi_cell(0, 7, "Вопросы к расписанию Жемчужненской средней школы", align="L")
    pdf.ln(3)
    pdf.body(LEAD, PENCIL)
    pdf.ln(2)

    number = 1
    pdf.heading("Где мы прочитали данные по-своему")
    for title, text in ASSUMED:
        pdf.numbered(number, title, text)
        number += 1

    pdf.heading("Часы, которые не сошлись с типовым учебным планом")
    pdf.body("Это не обязательно ошибка: школьный компонент и факультативы в план "
             "не входят, и школа вправе добавлять часы. Просто подтвердите, что так "
             "и задумано, — или скажите, где опечатка.", PENCIL)
    for line in data.get("plan", []):
        pdf.numbered(number, line)
        number += 1

    pdf.heading("Превышение предельной недельной нагрузки")
    pdf.body("Здесь уже норма, а не план: п. 93 ССЭТ № 525. Столько часов стоит "
             "в комплектовании, и расписание обязано их выдать.", PENCIL)
    for line in data.get("warnings", []):
        if "предельной норме" in line:
            pdf.numbered(number, line.split(" (")[0])
            number += 1

    pdf.heading("Чего система не знала")
    for title, text in NOT_KNOWN:
        pdf.numbered(number, title, text)
        number += 1

    pdf.heading("И главное — о самом расписании")
    for line in CHECK:
        pdf.numbered(number, line)
        number += 1

    pdf.ln(2)
    pdf.body("Ещё два места, где система сама знает, что вышло неидеально: "
             "у 11«А» и 11«Б» физкультура стоит два дня подряд. Три занятия при "
             "пятидневке должны идти через день, и вместе с остальными ограничениями "
             "так выходит не всегда. Обычный выход — перенести час в шестой школьный "
             "день; скажите, если он у вас используется.", PENCIL)

    out.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(out))
    return out


if __name__ == "__main__":
    school = sys.argv[1] if len(sys.argv) > 1 else "3e8bc4817797"
    target = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "out" / "voprosy.pdf"
    print("готово:", build(school, target))
