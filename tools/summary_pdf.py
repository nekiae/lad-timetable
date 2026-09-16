"""Саммари проекта одним PDF — то, что пересылают дальше по цепочке.

    .venv/bin/python tools/summary_pdf.py out/lad-summary.pdf

Текст живёт здесь, а не в docs/ONEPAGER.md: у листа своя вёрстка (две колонки цифр,
экраны с подписями), и держать два формата в одном markdown неудобно.
Скриншоты берутся из data/summary/ — снимаются tools/summary_shots.py.
Имена учителей и номер школы на экранах скрыты: документ уходит третьим лицам (§8.4).
"""
from __future__ import annotations

import sys
from pathlib import Path

from fpdf import FPDF
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
FONTS = ROOT / "data" / "fonts"
SHOTS = ROOT / "data" / "summary"

INK = (23, 32, 56)
PENCIL = (106, 116, 140)
PEN = (37, 66, 158)
RULE = (214, 220, 232)

TITLE = "ЛАД — автоматическое составление школьного расписания"
LEAD = ("Расписание уроков в школе составляют вручную около двух недель, и оно всё равно "
        "нарушает санитарные нормы. ЛАД составляет его за минуты по нормам Беларуси "
        "и на любое «почему нельзя» отвечает пунктом постановления.")

SECTIONS = [
    ("Задача", [
        "Завуч собирает расписание руками: бумага, карточки, Excel. Одновременно нужно свести "
        "учебный план, нагрузку полусотни учителей, кабинетный фонд и санитарные нормы — "
        "вручную это не удерживается, поэтому сентябрь школа живёт по временной сетке.",
        "В «Электронной школе» и на schools.by расписание вводится вручную: это хранение "
        "и отображение, генерации нет. А электронный журнал без корректного расписания не собрать.",
    ]),
    ("Что делает ЛАД", [
        "Составляет расписание за минуты. Движок — Google OR-Tools CP-SAT, санитарные нормы "
        "Беларуси (постановление № 206) зашиты из коробки, а не настраиваются вручную под чужой СанПиН.",
        "Принимает данные школы как есть. Школа загружает свою таблицу тарификации — система сама "
        "находит классы, учителей и часы (xlsx и старый xls). Ввод данных — те самые 80 % работы завуча.",
        "Объясняет каждое «нельзя». Завуч щёлкает урок и видит, куда его можно перенести, "
        "а на запрещённой клетке — причину словами и пункт нормы. Это аргумент в разговоре с учителем: "
        "не мнение завуча, а ссылка на постановление.",
        "Ставит силой и пересобирает. Если урок нужен именно здесь, он закрепляется, "
        "остальное система переставляет сама, двигая как можно меньше.",
        "Держит замены. Учитель заболел утром — на каждый урок предложены кандидаты с обоснованием, "
        "лист замен в чат учителей, журнал по датам для учёта часов.",
    ]),
]

MEASURED = [
    ("Время составления", "около двух недель", "первая законная сетка — 2–3 секунды"),
    ("Нарушений санитарных норм", "есть", "ноль в пяти прогонах из пяти"),
    ("Окон у учителей за неделю", "—", "59–71"),
]

LIMITS = [
    "Вердикта завуча-практика «это можно ставить в работу» ещё нет — это ближайший шаг.",
    "Вторая смена и межшкольные совместители не моделируются.",
    "Импорта из «Электронной школы» и schools.by нет; своя таблица Excel — есть.",
    "Нормы, невыполнимые в самих данных школы, система не прячет, а называет с советом.",
]

ASK = ("Не бюджета и не решения. Один вопрос: планируется ли в «Электронной школе» модуль "
       "автоматического составления расписания и кому правильно показать прототип.\n\n"
       "Позиция сознательная: не «ещё одна система для школ», а модуль расписания внутри "
       "государственной платформы. Движок — это HTTP-ручка, встраивается в чужой контур.")

SCREENS = [
    ("1-grid.png", "Готовая неделя школы: 24 класса, 428 строк нагрузки. "
                   "Сверху — время составления, нормы и окна у учителей."),
    ("2-highlight.png", "Щелчок по уроку: зелёные и жёлтые клетки — куда можно перенести, "
                        "красные — нельзя, с причиной и пунктом нормы."),
    ("3-substitutions.png", "Замены: кто проведёт уроки заболевшего учителя и журнал замен "
                            "за месяц для учёта часов."),
]


class Sheet(FPDF):
    def header(self) -> None:
        if self.page_no() == 1:
            return
        self.set_font("Plex", "", 8)
        self.set_text_color(*PENCIL)
        self.set_y(10)
        self.cell(0, 5, "ЛАД — автоматическое составление школьного расписания", align="L")
        self.ln(6)

    def footer(self) -> None:
        self.set_y(-14)
        self.set_font("Plex", "", 8)
        self.set_text_color(*PENCIL)
        self.cell(0, 5, f"Владислав Неки · Telegram @vladneki · сентябрь 2026", align="L")
        self.cell(0, 5, str(self.page_no()), align="R")

    def heading(self, text: str) -> None:
        self.ln(3)
        self.set_font("Plex", "B", 12)
        self.set_text_color(*INK)
        self.cell(0, 6, text)
        self.ln(7)

    def body(self, text: str) -> None:
        self.set_font("Plex", "", 9.5)
        self.set_text_color(*INK)
        # align="L": по умолчанию fpdf тянет строку по ширине, и в заголовке
        # с длинными словами между ними появляются провалы в полсантиметра.
        self.multi_cell(0, 4.6, text, align="L")
        self.ln(1.6)

    def bullet(self, text: str) -> None:
        self.set_font("Plex", "", 9.5)
        self.set_text_color(*INK)
        left = self.l_margin
        self.set_x(left)
        self.cell(4, 4.6, "—")
        self.multi_cell(self.w - left * 2 - 4, 4.6, text, align="L")
        self.ln(1.2)


def build(out: Path) -> Path:
    pdf = Sheet(format="A4")
    pdf.set_margins(18, 16, 18)
    pdf.set_auto_page_break(True, margin=18)
    pdf.add_font("Plex", "", str(FONTS / "IBMPlexSans-Regular.ttf"))
    pdf.add_font("Plex", "B", str(FONTS / "IBMPlexSans-SemiBold.ttf"))
    pdf.add_page()

    pdf.set_font("Plex", "B", 19)
    pdf.set_text_color(*INK)
    pdf.multi_cell(0, 8, TITLE, align="L")
    pdf.ln(1)
    pdf.set_font("Plex", "", 9)
    pdf.set_text_color(*PENCIL)
    pdf.cell(0, 5, "Логистика Академического Дня · прототип на данных реальной школы · сентябрь 2026")
    pdf.ln(9)

    pdf.set_font("Plex", "", 10.5)
    pdf.set_text_color(*INK)
    pdf.multi_cell(0, 5.2, LEAD, align="L")
    pdf.ln(2)

    for title, items in SECTIONS:
        pdf.heading(title)
        for item in items:
            pdf.bullet(item) if len(items) > 2 else pdf.body(item)

    pdf.heading("Что измерено")
    pdf.set_font("Plex", "", 9)
    pdf.set_text_color(*PENCIL)
    pdf.multi_cell(0, 4.4, "Реальная школа: 24 класса, 838 часов недельной нагрузки. "
                           "Метрики «было» и «стало» считает один и тот же валидатор.", align="L")
    pdf.ln(2)
    width = (pdf.w - pdf.l_margin - pdf.r_margin)
    cols = (width * 0.44, width * 0.26, width * 0.30)
    pdf.set_font("Plex", "B", 9)
    pdf.set_text_color(*INK)
    for text, w in zip(("", "Вручную", "ЛАД"), cols):
        pdf.cell(w, 6, text)
    pdf.ln(6)
    pdf.set_draw_color(*RULE)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(1.5)
    for name, was, now in MEASURED:
        pdf.set_font("Plex", "", 9.5)
        pdf.set_text_color(*INK)
        pdf.cell(cols[0], 6, name)
        pdf.set_text_color(*PENCIL)
        pdf.cell(cols[1], 6, was)
        pdf.set_font("Plex", "B", 9.5)
        pdf.set_text_color(*PEN)
        pdf.cell(cols[2], 6, now)
        pdf.ln(6)

    pdf.heading("Честные границы")
    for item in LIMITS:
        pdf.bullet(item)

    pdf.heading("Чего мы просим")
    pdf.body(ASK)

    pdf.add_page()
    pdf.heading("Как это выглядит")
    pdf.set_font("Plex", "", 9)
    pdf.set_text_color(*PENCIL)
    pdf.multi_cell(0, 4.4, "Экраны работающего прототипа. Фамилии учителей и школа скрыты.",
                   align="L")
    pdf.ln(3)
    # Ширина экранов подбирается под остаток листа, а не задаётся на глаз:
    # иначе стоит экрану стать выше — и последний уезжает на третью страницу.
    paths = []
    for name, _ in SCREENS:
        path = SHOTS / name
        if not path.exists():
            raise SystemExit(f"нет экрана {path} — сначала tools/summary_shots.py")
        paths.append(path)
    # Экраны идут в полную ширину колонки. Подгонять их под один лист пробовали —
    # сетка расписания становится нечитаемой, а ради неё лист и показывают;
    # лишняя страница дешевле, перенос fpdf делает сам.
    shot = pdf.w - pdf.l_margin - pdf.r_margin

    for path, (_, caption) in zip(paths, SCREENS):
        pdf.image(str(path), x=(pdf.w - shot) / 2, w=shot)
        pdf.ln(1.2)
        pdf.set_font("Plex", "", 8.5)
        pdf.set_text_color(*PENCIL)
        pdf.multi_cell(0, 4.2, caption, align="L")
        pdf.ln(3)

    out.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(out))
    return out


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "out" / "lad-summary.pdf"
    print("готово:", build(target))
