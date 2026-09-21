"""Разбор комплектования Жемчужненской СШ в таблицы ЛАД.

Источник — `data/raw/zhemchuzhny/komplektovanie.txt` (тарификация завуча,
свободная форма: «Ковригин Д. С. / Английский язык: 8абвг – 12 ч.»).
Разовый скрипт под одну школу, а не общий импорт: у общего есть
`lad.tarif_import`, он работает с Excel, а здесь Word с рукописной логикой.

Что делает:
  • строку «8абвг – 12 ч.» превращает в четыре строки нагрузки по 3 часа;
  • дробь «3/4» — часы первого и второго полугодий, берётся ПЕРВАЯ
    (расписание составляется на полугодие);
  • «Учитель белорусского языка и литературы: 5а – 5 ч.» раскладывает
    на язык и литературу по типовому плану № 75;
  • два учителя на один предмет в классе — это деление на подгруппы;
  • сверяет каждый класс с типовым планом и печатает расхождения.

Расхождения НЕ правятся молча: комплектование верстали поверх прошлогоднего,
часть параллелей съехала на год, и угадывать здесь нельзя. Список расхождений —
это вопросы завучу, а не дефект импорта.
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data/raw/zhemchuzhny/komplektovanie.txt"
OUT = ROOT / "data/zhemchuzhny.json"
PLAN = json.loads((ROOT / "data/plan_75.json").read_text(encoding="utf-8"))

# --- школа: классы, смены, кабинеты (печатная таблица 12_klassy_kabinety.png)

ROOM_BY_CLASS = {
    "5А": "36", "5Б": "31", "5В": "25", "5Г": "27",
    "6А": "26", "6Б": "29", "6В": "30", "6Г": "24",
    "7А": "36", "7Б": "37", "7В": "38", "7Г": "33",
    "8А": "30", "8Б": "29", "8В": "12", "8Г": "26",
    "9А": "28", "9Б": "38", "9В": "37", "9Г": "24", "9Д": "33",
    "10А": "10", "11А": "11", "11Б": "14",
}
SECOND_SHIFT = {c for c in ROOM_BY_CLASS if c[0] in "67" and not c.startswith("1")}

# Спецкабинеты — со слов завуча. Спортзал в списке не значился: он один,
# и завуч говорит, что «спокойно вмещается два класса, можно три».
SPECIAL_ROOMS = [
    ("4", "мастерская (техтруд)", 20, 1),
    ("13", "мастерская (обсл. труд)", 20, 1),
    ("22", "компьютерный", 15, 1),
    ("35", "компьютерный", 15, 1),
    ("23", "физика", 30, 1),
    ("10", "химия", 30, 1),
    ("11", "биология", 30, 1),
    ("14", "допризывная подготовка", 30, 1),
    ("9", "обычный", 30, 1),   # лингафонный
    ("32", "обычный", 30, 1),  # музыка
    ("спортзал", "спортзал", 60, 4),
]

# --- разбор

FIO = re.compile(r"^([А-ЯЁ][а-яё]+)\s+([А-ЯЁ])[а-яё]*\.?\s*([А-ЯЁ])[а-яё]*\.?\s*$")
# «8абвг – 12 ч.», «9а -2 ч.», «11аб – 3 ч.(профиль)», «7а –3/4 ч.»
# «11б (проф.) – 4 ч»: пометка уровня стоит между классом и часами,
# и без неё запись просто не находится — а часы уходят соседнему классу.
HOURS = re.compile(r"(\d{1,2})\s*([а-дА-Д]*)\s*(\([^)]*\))?\s*[-–—]\s*"
                   r"(\d+)(?:\s*/\s*(\d+))?\s*ч", re.I)

SUBJECT_WORDS = [
    ("математик", "Математика"), ("астроном", "Астрономия"),
    ("физик", "Физика"), ("хими", "Химия"), ("биолог", "Биология"),
    ("географ", "География"), ("человек и мир", "Человек и мир"),
    ("информатик", "Информатика"), ("черчение", "Черчение"),
    ("обществов", "Обществоведение"), ("мхк", "МХК"), ("искусств", "МХК"),
    ("физическ", "Физическая культура и здоровье"),
    ("физкультур", "Физическая культура и здоровье"),
    ("истори", "История"), ("английск", "Английский язык"),
    ("немецк", "Немецкий язык"), ("белорусск", "Белорусский язык и литература"),
    ("русск", "Русский язык и литература"), ("физическая культура", "Физическая культура и здоровье"),
    ("трудов", "Трудовое обучение"), ("обж", "ОБЖ"),
    ("допр", "Допризывная и медицинская подготовка"),
    ("мед. подг", "Допризывная и медицинская подготовка"),
    ("мед подг", "Допризывная и медицинская подготовка"),
]

# Пары «язык + литература» одной строкой: как разложить по плану № 75.
PAIRS = {
    "Белорусский язык и литература": ("Белорусский язык", "Белорусская литература"),
    "Русский язык и литература": ("Русский язык", "Русская литература"),
}
PLAN_HOURS = {s["name"]: s["hours"] for s in PLAN["subjects"]}
PLAN_ROOM = {s["name"]: s["room"] for s in PLAN["subjects"]}
# Наши названия → названия типового плана (для сверки часов).
TO_PLAN = {
    "Английский язык": "Иностранный язык", "Немецкий язык": "Иностранный язык",
    "МХК": "Искусство (отечественная и мировая художественная культура)",
    "ОБЖ": "Основы безопасности жизнедеятельности",
}


def find_subject(text: str) -> str | None:
    low = text.lower()
    for key, name in SUBJECT_WORDS:
        if key in low:
            return name
    return None


def short_name(full: str) -> str:
    parts = full.replace(" ", " ").split()
    if len(parts) >= 3:
        return f"{parts[0]} {parts[1][0]}. {parts[2][0]}."
    if len(parts) == 2 and "." in parts[1]:
        letters = [c for c in parts[1] if c.isupper()]
        if len(letters) == 2:
            return f"{parts[0]} {letters[0]}. {letters[1]}."
    return full.strip()


def glue(text: str) -> str:
    """Склеить то, что Word разорвал по строкам.

    В комплектовании «Калько» и «Анастасия Александровна» стоят на разных
    строках, а «Учитель» отделён от «математики». Без склейки часы Калько
    достаются предыдущему учителю — и у 5«Г» выходит шесть часов английского
    вместо трёх.
    """
    lines = [l.strip() for l in text.split("\n")]
    out, i = [], 0
    while i < len(lines):
        line = lines[i]
        nxt = next((j for j in range(i + 1, len(lines)) if lines[j]), None)
        if nxt is not None:
            tail = lines[nxt]
            one = re.fullmatch(r"[А-ЯЁ][а-яё]+", line)
            two = re.fullmatch(r"[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+", tail)
            if line.lower() == "учитель" or (one and two):
                line, i = f"{line} {tail}", nxt
        out.append(line)
        i += 1
    return "\n".join(out)


# Строки комплектования, исправленные со слов завуча. Слева — как написано,
# справа — как есть на самом деле.
LINE_FIX = {
    # Информатика идёт во всех девятых, а «д» потерялась: 5 часов на 4 класса.
    "9 абвг – 5 ч.,": "9абвгд – 5 ч.,",
    # Восьмых классов четыре: лишняя «д» у информатики — след прошлого года.
    "8абвгд – 5 ч.,": "8абвг – 4 ч.,",
    # Хоровец ведёт седьмые и восьмые классы, а не девятые (ответ завуча).
    "Биология: 9абвг - 8 ч., 7абвг - 8 ч.,": "Биология: 8абвг - 8 ч., 7абвг - 8 ч.,",
    # «10, 11аб – 3 ч.» — это по часу каждому из трёх классов.
    "10, 11аб – 3 ч.": "10 – 1 ч., 11аб – 1 ч.",
}


# Не ответы завуча, а НАШИ предположения: без них школа не считается,
# но подтвердить их обязательно. Печатаются отдельным списком.
ASSUMED = {
    # У 7«А» русский 4 часа (Воробей, «7а – 4/3 ч.») и столько же по типовому
    # плану. У Леончук на 7«Б», 7«В» и 7«Г» стоит 15 часов — это 5 на класс,
    # и тогда класс не помещается во вторую смену. Читаем как 12.
    "7бвг – 15 ч.,": ("7бвг – 12 ч.,",
                      "у 7Б, 7В, 7Г русский 4 ч, а не 5: иначе класс "
                      "не помещается во вторую смену"),
}


def parse(text: str) -> list[dict]:
    for wrong, right in LINE_FIX.items():
        text = text.replace(wrong, right)
    for wrong, (right, _) in ASSUMED.items():
        text = text.replace(wrong, right)
    text = glue(text)
    rows: list[dict] = []
    teacher = None
    subject = None
    for raw in text.split("\n"):
        line = raw.strip()
        if not line:
            continue
        words = line.split()
        if 2 <= len(words) <= 3 and not HOURS.search(line) and all(
                w[0].isupper() for w in words if w[0].isalpha()):
            if FIO.match(line) or re.match(r"^[А-ЯЁ][а-яё]+\s+[А-ЯЁ]\.\s*[А-ЯЁ]\.$", line):
                teacher, subject = short_name(line), None
                continue
        if not HOURS.search(line):
            found = find_subject(line)
            if found:
                subject = found
            continue
        head = line[: HOURS.search(line).start()]
        found = find_subject(head) if head.strip(" :.,–-") else None
        if found:
            subject = found
        # «Профиль» относится к конкретному классу, а не ко всей строке:
        # у Барсуковой «8аг – 10 ч., 9б – 5 ч.(профиль)» повышенный уровень
        # только у 9«Б». Пометку ищем рядом с часами — она стоит и после
        # («5 ч.(профиль)»), и перед («10 (проф.) – 4 ч»).
        spots = list(HOURS.finditer(line))
        for number, found in enumerate(spots):
            # Пометка «(профиль)» относится к СВОЕМУ классу: у Жихарко
            # «10 – 4 ч., 11б (проф) – 6 ч.» повышенный уровень только у 11«Б».
            # Поэтому смотрим строго между соседними записями часов.
            left = spots[number - 1].end() if number else 0
            right = spots[number + 1].start() if number + 1 < len(spots) else len(line)
            near = line[left:right].lower()
            advanced = "проф" in near or "повышен" in near
            parallel, letters, mark, first, _second = found.groups()
            near = f"{near} {mark or ''}".lower()
            letters = (letters or "").upper() or " "
            names = [f"{parallel}{ch}".strip() for ch in letters]
            per = share(int(first), names, subject, advanced)
            for name in names:
                rows.append({"teacher": teacher, "subject": subject, "class": name,
                             "hours": per, "advanced": advanced, "source": line})
    return rows


def share(hours: int, names: list[str], subject: str | None, advanced: bool) -> float:
    """Сколько часов достаётся одному классу из строки «8абвг – 12 ч.».

    Завуч пишет двояко: «6аб – 10 ч.» — это по 5 на класс, а «11аб – 3 ч.» —
    по 3 на каждый. Разрешает спор типовой план: берём то прочтение, которое
    с ним сходится. Если не сходится ни одно — делим поровну и выносим строку
    в расхождения.
    """
    if not subject:
        return hours / len(names)
    # Профильную строку сверяем и с повышенными часами, и с базовыми:
    # «11аб – 3 ч.(профиль)» — это 3 часа каждому классу, а не полтора.
    for level in ({True, False} if advanced else {False}):
        want = plan_hours(subject, names[0], level)
        if not want:
            continue
        if abs(hours / len(names) - want) < 0.01:
            return hours / len(names)
        if abs(hours - want) < 0.01:
            return float(hours)
    return hours / len(names)


def expand_pairs(rows: list[dict]) -> list[dict]:
    """«5А – 5 ч.» у словесника → язык 3 ч + литература 2 ч (план № 75)."""
    out = []
    for row in rows:
        pair = PAIRS.get(row["subject"] or "")
        if not pair:
            out.append(row)
            continue
        parallel = re.match(r"\d+", row["class"]).group()
        a, b = (PLAN_HOURS[name].get(parallel) for name in pair)
        if a is None or b is None or a + b != row["hours"]:
            row = dict(row, note=f"не раскладывается по плану: {row['hours']:g} ч "
                                 f"≠ {a} + {b}")
            out.append(row)
            continue
        for name, hours in zip(pair, (a, b)):
            out.append(dict(row, subject=name, hours=hours))
    return out


# --- исправления со слов завуча (21.09.2026, docs/PILOT_ZHEMCHUZHNY.md)
# Комплектование верстали поверх прошлогоднего: «прошлогодняя 8 — нынешняя 9».
# Восьмых классов пять не бывает, «8Д» везде читается как 9«Д».
CLASS_FIX = {"8Д": "9Д", "10": "10А", "11": "11А", "56": "5Б"}

# Физкультура в X–XI: 3 часа, из них 2 в подгруппах (Дударенко — девочки,
# Борисевич — мальчики), третий урок Борисевич ведёт весь класс вместе.
PE_SENIOR = {"10А", "11А", "11Б"}

# Предметы, которые школа делит на подгруппы. Если предмет в классе ведут
# двое — это деление, а не двойная нагрузка класса.
SPLIT_SUBJECTS = {"Английский язык", "Немецкий язык", "Информатика",
                  "Трудовое обучение", "Физическая культура и здоровье",
                  "Допризывная и медицинская подготовка"}
# Кто в какой подгруппе у труда: мастерская и обслуживающий труд.
TRUD_ROOM = {"Буза А. С.": "мастерская (техтруд)",
             "Сычик М. И.": "мастерская (обсл. труд)",
             "Мисюн А. А.": "мастерская (обсл. труд)"}


def apply_fixes(rows: list[dict]) -> list[dict]:
    out = []
    for row in rows:
        name = CLASS_FIX.get(row["class"].strip(), row["class"].strip())
        row = dict(row, **{"class": name})
        if (row["subject"] == "Физическая культура и здоровье"
                and name in PE_SENIOR and row["hours"] == 3):
            out.append(dict(row, hours=2, part="мальчики"))
            out.append(dict(row, hours=1, part=""))
            continue
        if (row["subject"] == "Физическая культура и здоровье"
                and name in PE_SENIOR and row["hours"] == 2):
            out.append(dict(row, part="девочки"))
            continue
        out.append(row)
    return out


def assign_parts(rows: list[dict]) -> list[dict]:
    """Два учителя на один предмет в классе — это подгруппы."""
    by_key: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        by_key[(row["class"], row["subject"] or "")].append(row)
    for (class_name, subject), group in by_key.items():
        teachers = {row["teacher"] for row in group}
        if len(teachers) < 2:
            continue
        # Профильная группа — тоже деление: часть класса берёт предмет
        # на повышенном уровне у одного учителя, остальные на базовом у другого.
        levels = {row["advanced"] for row in group}
        if levels == {True, False}:
            for row in group:
                row["part"] = "повышенная" if row["advanced"] else "базовая"
                # Спецкабинет один, и обе группы в него не поместятся:
                # профильная идёт в него, базовая — в обычный класс.
                if not row["advanced"]:
                    row["room"] = "обычный"
            continue
        if subject not in SPLIT_SUBJECTS:
            continue
        if any(row.get("part") for row in group):
            continue
        order = sorted(teachers)
        for row in group:
            if subject == "Трудовое обучение":
                room = TRUD_ROOM.get(row["teacher"], "мастерская (обсл. труд)")
                row["part"] = ("мальчики" if room == "мастерская (техтруд)"
                               else "девочки")
                row["room"] = room
            else:
                row["part"] = str(order.index(row["teacher"]) + 1)
                # Кабинет допризывной подготовки один: девушки на медицинской
                # подготовке занимаются в обычном классе.
                if subject.startswith("Допризывная") and row["teacher"] != "Трус А. Н.":
                    row["room"] = "обычный"
    return rows


# В типовом плане история — это два предмета в V–IX и один в X–XI.
# Школа пишет одной строкой «История», поэтому сверяем с суммой.
HISTORY = ("Всемирная история", "История Беларуси",
           "История Беларуси в контексте всемирной истории")


def plan_hours(subject: str, class_name: str, advanced: bool):
    if subject == "История":
        parts = [plan_hours(name, class_name, advanced) for name in HISTORY]
        return sum(p for p in parts if p) or None
    pair = PAIRS.get(subject)
    if pair:
        parts = [plan_hours(name, class_name, advanced) for name in pair]
        return sum(p for p in parts if p) or None
    name = TO_PLAN.get(subject, subject)
    entry = next((s for s in PLAN["subjects"] if s["name"] == name), None)
    if entry is None:
        return None
    parallel = re.match(r"\d+", class_name).group()
    if advanced and entry.get("hours_advanced", {}).get(parallel):
        return entry["hours_advanced"][parallel]
    return entry["hours"].get(parallel)


def report(rows: list[dict]) -> list[str]:
    """Расхождения с типовым планом — вопросы завучу, а не ошибки импорта."""
    problems = []
    for row in rows:
        if row.get("note"):
            problems.append(f"{row['class']}, «{row['subject']}»: {row['note']}"
                            f"   ← {row['source']}")
        if row["subject"] is None:
            problems.append(f"{row['class']}: не понят предмет   ← {row['source']}")
        elif row["hours"] != int(row["hours"]):
            problems.append(f"{row['class']}, «{row['subject']}», "
                            f"{row['teacher']}: {row['hours']:g} часа на класс — "
                            f"дробь   ← {row['source']}")
    by_key: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        if row["subject"]:
            by_key[(row["class"], row["subject"])].append(row)
    for (class_name, subject), group in sorted(by_key.items()):
        by_part: dict[str, list[dict]] = defaultdict(list)
        for row in group:
            by_part[row.get("part") or ""].append(row)
        # Час, который класс берёт целиком, достаётся каждой подгруппе:
        # в X–XI два урока физкультуры идут по группам, а третий — всем вместе.
        whole = sum(row["hours"] for row in by_part.get("", []))
        for part, rows_of_part in by_part.items():
            if part == "" and len(by_part) > 1:
                continue
            advanced = any(row["advanced"] for row in rows_of_part)
            want = plan_hours(subject, class_name, advanced)
            if want is None:
                continue
            # Часы повышенного уровня в V–IX типовой план не задаёт: школа
            # определяет их сама, и сверять там нечего.
            if advanced and plan_hours(subject, class_name, False) == want:
                continue
            have = sum(row["hours"] for row in rows_of_part) + (whole if part else 0)
            if abs(have - want) > 0.01:
                who = ", ".join(sorted({row["teacher"] or "?" for row in rows_of_part}))
                label = f" ({part})" if part else ""
                problems.append(f"{class_name}, «{subject}»{label}: {have:g} ч, "
                                f"по плану {want} ч ({who})")
    return problems


def only_senior(rows: list[dict]) -> list[dict]:
    """Оставить V–XI.

    В комплектовании есть часы английского в третьих и четвёртых классах,
    но начальную школу мы не составляем: её учителей в документе нет.
    Побочный эффект известен и назван в docs/PILOT_ZHEMCHUZHNY.md: эти часы
    не займут учителя, и в его расписании они будут выглядеть свободными.
    """
    return [row for row in rows
            if int(re.match(r"\d+", row["class"]).group()) >= 5]


def dedupe(rows: list[dict]) -> list[dict]:
    """Одна и та же строка дважды — это опечатка, а не двойная нагрузка.

    У Горбель белорусский в десятом записан и как «10», и как «10а»; класс
    один, значит и строка одна.
    """
    seen, out = set(), []
    for row in rows:
        key = (row["class"], row["subject"], row["teacher"], row["hours"])
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    # Один и тот же предмет в одном классе у нескольких учителей с одинаковыми
    # часами — тоже след копипасты: белорусский в десятом записан трижды,
    # по три часа, хотя класс один и по плану часов три. Оставляем первого
    # по документу, остальных выносим в вопросы: кто из них ведёт на самом
    # деле, знает только завуч.
    kept: dict[tuple[str, str, float], str] = {}
    result = []
    for row in out:
        if row.get("part") or row["subject"] in SPLIT_SUBJECTS:
            result.append(row)
            continue
        key = (row["class"], row["subject"], row["hours"])
        if key in kept and kept[key] != row["teacher"]:
            row["note"] = (f"этот предмет в классе записан ещё и на "
                           f"{kept[key]} — строка отброшена, кто ведёт?")
            row["dropped"] = True
            result.append(row)
            continue
        kept.setdefault(key, row["teacher"])
        result.append(row)
    return result


def tables(rows: list[dict]) -> dict:
    classes = sorted(ROOM_BY_CLASS, key=lambda c: (int(re.match(r"\d+", c).group()), c))
    advanced_classes = {row["class"] for row in rows if row["advanced"]}
    teachers = sorted({row["teacher"] for row in rows if row["teacher"]})
    subjects = sorted({row["subject"] for row in rows if row["subject"]})
    plain = sorted(set(ROOM_BY_CLASS.values()) - {r[0] for r in SPECIAL_ROOMS},
                   key=lambda x: (len(x), x))
    rooms = [{"кабинет": n, "тип": k, "мест": seats, "классов сразу": at_once}
             for n, k, seats, at_once in SPECIAL_ROOMS]
    rooms += [{"кабинет": n, "тип": "обычный", "мест": 30, "классов сразу": 1}
              for n in plain]
    load = []
    for row in rows:
        if not row["subject"] or not row["teacher"] or row.get("dropped"):
            continue
        load.append({
            "класс": row["class"], "предмет": row["subject"],
            "учитель": row["teacher"], "часов": round(row["hours"]),
            "подгруппа": row.get("part") or "",
            "уровень": "повышенный" if row["advanced"] else "базовый",
            "тип": "урок", "кабинет": row.get("room") or "—",
        })
    return {
        # Звонки школы: первая смена 8:10–15:40 (восемь уроков), вторая
        # 14:00–19:30 (шесть). 14:00 — это седьмой урок первой смены и первый
        # второй, то есть ось одна, а вторая смена начинается с седьмого.
        "settings": {"name": "Жемчужненская средняя школа", "periods": 8,
                     "вторая смена с урока": 7, "уроков во второй смене": 6,
                     "days": 5, "sixth_day": True, "intro_seen": True},
        "tables": {
            "classes": [{"класс": c, "учеников": 24,
                         "смена": "2" if c in SECOND_SHIFT else "1",
                         "повышенный уровень": c in advanced_classes} for c in classes],
            "subjects": [{"предмет": s,
                          "кабинет": PLAN_ROOM.get(TO_PLAN.get(s, s), "обычный"),
                          "только в нём": False, "всегда парой": False} for s in subjects],
            "teachers": [{"ФИО": t, "методический день": "", "свой кабинет": "—",
                          "уроков в день": "", "совместитель": False} for t in teachers],
            "rooms": rooms,
            "load": load,
        },
        "wishes": {},
    }


def main() -> int:
    rows = only_senior(apply_fixes(expand_pairs(parse(SRC.read_text(encoding="utf-8")))))
    rows = assign_parts(dedupe(rows))
    problems = report(rows)
    data = tables(rows)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    load = data["tables"]["load"]
    print(f"{OUT.relative_to(ROOT)}: {len(load)} строк нагрузки, "
          f"{sum(r['часов'] for r in load)} часов, "
          f"{len(data['tables']['teachers'])} учителей")
    print("\nПредположения (подтвердить у завуча):")
    for _, (_, why) in ASSUMED.items():
        print(" •", why)
    print(f"\nРасхождений: {len(problems)}")
    for line in problems:
        print(" •", line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
