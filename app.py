"""ЛАД — рабочее место завуча.

Запуск:  .venv/bin/streamlit run app.py

Здесь вводятся данные школы и нажимается «Составить». Результат — HTML-файл,
который скачивается и пересылается кому угодно (CLAUDE.md §7.1: Streamlit —
рабочее место, HTML — то, что уходит наружу).

Устройство ввода:
  • первый запуск ведёт МАСТЕР — шесть шагов, на выходе заполненные таблицы;
  • дальше завуч живёт в ТАБЛИЦАХ: править одну строку быстрее, чем идти по шагам;
  • пожелания учителей вводятся СЕТКОЙ день × урок, отдельно «не может»
    и «нежелательно» — это разные вещи (см. tables.CANT / tables.DISLIKE);
  • нормы вынесены на отдельную вкладку с переключателями строгости, потому что
    норма — требование к школе, а не к алгоритму, и завуч отвечает за то,
    какую из них он готов ослабить.
"""

import hashlib
import json
import sys
import time
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent / "src"))

from lad.excel import to_bytes as excel_bytes
from lad.intro import show as show_intro
from lad.job import SolveJob
from lad.render import render
from lad.solve import PRESETS, RULE_SOURCES, RULE_TITLES, Rules, Weights, assign_rooms, diagnose, solve
from lad.storage import save_schedule
from lad.style import inject as inject_style
from lad.tables import (
    CANT, DATA_FILE, DAY_NAMES, DISLIKE, NONE_CHOICE, ROOM_KINDS, WISH_OPTIONS, blank_tables, build_school, tables_from_dict,
    LESSON_KINDS, LEVELS, add_subject_slots, apply_profile, assign_teacher, check_norms,
    slot_label,
    compare_with_plan,
    generate_classes, split_subjects, spread_evenly, subject_progress, subject_slots,
    teacher_hours,
    generate_load, generate_rooms, generate_subjects, grid_to_wishes, input_status, load_plan,
    load_tables, load_wishes, next_step, parallels_of, plan_summary, save_tables, wishes_to_grid,
)
from lad.validate import check

st.set_page_config(page_title="ЛАД — составление расписания", page_icon=":material/calendar_month:", layout="wide")

inject_style()

OUT_HTML = Path("out/raspisanie.html")
STRICTNESS = {"жёстко": "hard", "мягко": "soft", "не применять": "off"}

# ------------------------------------------------------------------ состояние

if "tables" not in st.session_state:
    st.session_state.tables = load_tables()
    raw = json.loads(DATA_FILE.read_text(encoding="utf-8")) if DATA_FILE.exists() else {}
    st.session_state.settings = raw.get("settings", {})
    st.session_state.wishes = load_wishes()
    # Интро — до мастера и до всего остального: сначала «что это вообще»,
    # потом «введите классы». Обратный порядок бессмысленен.
    st.session_state.intro = not st.session_state.settings.get("intro_seen")
    st.session_state.intro_slide = 0

tables = st.session_state.tables
settings = st.session_state.settings

# ------------------------------------------------------------------ интро
# Идёт до заголовка: на экране интро он лишний — карточка и так называет продукт.

def finish_intro() -> None:
    settings["intro_seen"] = True
    save_tables(tables, settings, st.session_state.wishes)
    st.session_state.intro = False
    st.rerun()


if st.session_state.get("intro"):
    show_intro(settings, finish_intro)
    st.stop()


# ------------------------------------------------------------------ мастер

st.title("ЛАД")
st.caption("Логистика Академического Дня — составление школьного расписания")


# ------------------------------------------------------------------ сайдбар

def rooms_verdict(tables: dict) -> list[str]:
    """Хватает ли кабинетов — по одним лишь классам и кабинетам.

    Класс учится без окон, поэтому на первом уроке заняты ВСЕ классы разом,
    и каждому нужна комната. Это чистая арифметика, для неё не нужны ни
    нагрузка, ни учителя, — а значит, ответ можно дать в самом начале ввода.
    """
    classes = [c for c in tables["classes"].get("класс", []) if str(c).strip()]
    if not classes or not len(tables["rooms"]):
        return []

    seats = 0
    for _, row in tables["rooms"].iterrows():
        if not str(row.get("кабинет", "")).strip():
            continue
        seats += max(1, int(row.get("классов сразу") or 1))

    if seats >= len(classes):
        return []
    return [
        f"Классов {len(classes)}, а кабинеты вмещают {seats} за раз. "
        "Класс учится без окон, поэтому на первом уроке заняты все классы "
        "сразу — и мест нужно не меньше, чем классов. Расписания в одну смену "
        "не существует: добавьте кабинеты или переведите часть классов "
        "во вторую смену."
    ]


def school_file_bytes(tables: dict, settings: dict, wishes: dict) -> bytes:
    """Собрать файл школы — тот же формат, что и data/school.json.

    Отдельная функция, а не save_tables: сохранять надо не на диск программы,
    а в руки завучу.
    """
    payload = {
        "settings": settings,
        "tables": {name: df.to_dict("records") for name, df in tables.items()},
        "wishes": wishes,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


# Название школы и размер сетки живут на ПЕРВОМ ШАГЕ, а не здесь. В боковой
# панели их легко не заметить, а от них зависит всё остальное. Здесь остаётся
# то, что настраивают уже перед самым составлением, и то, что нужно в любой
# момент: файл со школой и справка.
with st.sidebar:
    st.caption(f"**{settings.get('name') or 'Школа не названа'}** · "
               f"{settings.get('periods', 8)} уроков в день · "
               f"{settings.get('days', 5)} дней")

    st.divider()
    st.subheader("Чьё удобство важнее")
    st.caption("Всем сразу угодить нельзя: меньше окон у учителей — неровнее дни "
               "у классов, и наоборот. Выберите, куда склонять.")
    preset_name = st.radio("Приоритет", list(PRESETS), label_visibility="collapsed")
    st.caption(PRESETS[preset_name]["about"])

    st.divider()
    st.subheader("Сколько ждать")
    st.caption("Система ищет лучший вариант, пока есть время. Дольше ищет — меньше "
               "окон и ровнее дни. Расписание получится в любом случае.")
    # Значение по умолчанию — не «быстро попробовать», а «хватит на школу».
    # Замерено 25.08.2026 на 28 классах и 980 часах: со всеми нормами в жёстком
    # режиме первое законное расписание находится за 119 секунд. С бюджетом
    # в полминуты завуч получал бы «решения нет» там, где решение есть.
    budget = st.select_slider(
        "Время на поиск", options=[60, 120, 300, 600, 900], value=300,
        format_func=lambda v: {60: "минута — только для маленькой школы",
                               120: "2 минуты", 300: "5 минут — рекомендуем",
                               600: "10 минут", 900: "15 минут"}[v],
        label_visibility="collapsed")

    weights = PRESETS[preset_name]["weights"]
    with st.expander("Тонкая настройка"):
        st.caption("Здесь те же приоритеты, но числами. Чем больше число, тем сильнее "
                   "система избегает этой неприятности. Трогать не обязательно — "
                   "значения подставлены выбором выше.")
        w_gap = st.slider("Окно у учителя", 0, 20, weights.teacher_gap, key=f"teacher_gap_{preset_name}",
                          help="Свободный урок в середине дня: учитель в школе, но без дела.")
        w_day = st.slider("Лишний выход учителя в школу", 0, 20, weights.teacher_day, key=f"teacher_day_{preset_name}",
                          help="Приезд ради одного-двух уроков. Чем выше, тем плотнее "
                               "система соберёт уроки учителя в меньшее число дней.")
        w_bal = st.slider("Неровные дни у класса", 0, 20, weights.class_imbalance, key=f"class_imbalance_{preset_name}",
                          help="Когда в один день 8 уроков, а в другой 3.")
        w_diff = st.slider("Неровная трудность по дням", 0, 20, weights.difficulty_imbalance, key=f"difficulty_imbalance_{preset_name}",
                           help="Санитарные нормы требуют распределять нагрузку с учётом "
                                "шкалы трудности предметов (п. 88.2). День с физикой, "
                                "химией и математикой тяжелее дня с физкультурой и трудом, "
                                "даже если уроков поровну.")
        w_wish = st.slider("Пожелание учителя", 0, 20, weights.teacher_wish, key=f"teacher_wish_{preset_name}",
                           help="Цена нарушения «нежелательно». Запреты «не может» "
                                "не нарушаются никогда, независимо от этого числа.")
        weights = Weights(teacher_gap=w_gap, teacher_day=w_day, class_imbalance=w_bal,
                          difficulty_imbalance=w_diff, teacher_wish=w_wish)

    st.divider()
    # ГЛАВНАЯ ЗАЩИТА ВВЕДЁННОГО. Данные лежат в файле рядом с программой, и на
    # своей машине этого достаточно. Но в интернете программа живёт в контейнере,
    # который перезапускается сам по себе — заснул на сутки, обновилась версия, —
    # и файловая система возвращается к исходной. Введённая школа при этом
    # пропадает целиком.
    #
    # Поэтому файл со школой можно забрать себе. Это единственный способ не
    # потерять несколько часов работы, и он должен быть на виду, а не в углу.
    st.subheader("Ваши данные")
    st.caption("Скачайте файл после ввода. Программа в интернете иногда "
               "перезапускается и забывает всё, что не сохранено у вас.")

    st.download_button(
        "Скачать файл школы", data=school_file_bytes(tables, settings,
                                                     st.session_state.wishes),
        file_name=f"{settings.get('name', 'школа')}.json".replace("/", "-"),
        mime="application/json", width="stretch", icon=":material/download:",
        help="Все введённые классы, учителя, кабинеты, нагрузка и пожелания "
             "одним файлом. Сохраните его себе.")

    restored = st.file_uploader("Загрузить файл школы", type="json",
                                label_visibility="collapsed",
                                help="Вернуть данные из ранее скачанного файла.")
    if restored is not None and st.session_state.get("restored_name") != restored.name:
        try:
            payload = json.loads(restored.getvalue().decode("utf-8"))
            # Через ту же дверь, что и файл с диска: файл, сохранённый прежней
            # версией, придёт без новых колонок, и их надо дополнить — иначе
            # в таблице их просто не будет видно.
            st.session_state.tables = tables_from_dict(payload)
            st.session_state.settings = payload.get("settings", {})
            st.session_state.wishes = payload.get("wishes", {})
            st.session_state.restored_name = restored.name
            save_tables(st.session_state.tables, st.session_state.settings,
                        st.session_state.wishes)
            for stale in ("job", "result_of", "result_view", "done_for"):
                st.session_state.pop(stale, None)
            st.success("Данные загружены.")
            st.rerun()
        except Exception as error:  # noqa: BLE001 — показываем как есть
            st.error(f"Не получилось прочитать файл: {error}")

    st.divider()
    if st.button("Как это работает", width="stretch", icon=":material/help:"):
        st.session_state.intro = True
        st.session_state.intro_slide = 0
        st.rerun()


status = input_status(tables, st.session_state.wishes)
by_key = {step["key"]: step for step in status}

# ------------------------------------------------------------------ шаги
#
# Ввод школы — это ПРОЦЕСС, а не набор таблиц: у него есть начало, порядок
# и конец. Вкладки этого не показывают — по ним не видно, где ты, что дальше
# и сколько осталось; вдобавок Streamlit не умеет переключать их из кода,
# поэтому кнопки «Дальше» на вкладках быть не может в принципе.
#
# Порядок продуман, а не унаследован от таблиц:
#   1. Школа    — рамка сетки: сколько уроков в дне и дней в неделе. Раньше
#                 пряталась в боковой панели, где её легко не заметить, хотя
#                 от неё зависит всё остальное.
#   2. Классы   — для кого расписание.
#   3. Кабинеты — СРАЗУ после классов, потому что нехватку кабинетов видно
#                 чистой арифметикой, без нагрузки и учителей. Узнать об этом
#                 надо на второй минуте, а не через три часа ввода.
#   4. Предметы — набирается кнопкой из типового плана.
#   5. Учителя  — список тех, кто ведёт.
#   6. Нагрузка — самое долгое; к ней подходим, когда всё остальное готово.
#   7. Пожелания — необязательный шаг.
#   8. Проверка — сверка с учебным планом и санитарные нормы.
#   9. Составить.
STEPS = [
    {"n": 0, "title": "Школа", "sub": "название и сетка", "key": None},
    {"n": 1, "title": "Классы", "sub": "кто учится", "key": "classes"},
    {"n": 2, "title": "Кабинеты", "sub": "где учатся", "key": "rooms"},
    {"n": 3, "title": "Предметы", "sub": "что изучают", "key": "subjects"},
    {"n": 4, "title": "Учителя", "sub": "кто ведёт", "key": "teachers"},
    {"n": 5, "title": "Нагрузка", "sub": "кто что ведёт", "key": "load"},
    {"n": 6, "title": "Пожелания", "sub": "можно пропустить", "key": "wishes"},
    {"n": 7, "title": "Проверка", "sub": "план и нормы", "key": None},
    {"n": 8, "title": "Составить", "sub": "результат", "key": None},
]
LAST_STEP = STEPS[-1]["n"]

if "ui_step" not in st.session_state:
    # Начинаем не с первого шага, а с первого НЕЗАПОЛНЕННОГО: вернувшись
    # к работе, завуч попадает туда, где остановился.
    todo = next_step(status)
    st.session_state.ui_step = next(
        (s["n"] for s in STEPS if todo and s["key"] == todo["key"]), 0)

step_now = st.session_state.ui_step


def step_state(step: dict) -> str:
    """done — заполнено, now — здесь мы сейчас, wait — ещё не дошли."""
    if step["n"] == step_now:
        return "now"
    info = by_key.get(step["key"]) if step["key"] else None
    return "done" if (info and info["done"]) else "wait"


def go(n: int) -> None:
    st.session_state.ui_step = max(0, min(LAST_STEP, n))
    st.rerun()


# Лента шагов: и указатель, и навигация. Порядок читается с одного взгляда —
# у каждого шага номер, между ними стрелки, пройденный помечен галочкой.
#
# В кнопке ТОЛЬКО номер и название. Счётчик («Классы · 14») пробовали держать
# здесь же — и он ломал всю ленту: на девять кнопок в ряд приходится около ста
# пикселей ширины, текст переносился где попало (слово «Предметы» разрывалось
# пополам), кнопки выходили разной высоты, лента скакала. Сколько чего введено,
# видно на самом шаге и в подписи под лентой — там для этого есть место.
done_count = sum(1 for step in STEPS if step_state(step) == "done")
total_required = sum(1 for s in STEPS if s["key"])

widths, order = [], []
for step in STEPS:
    if order:
        widths.append(0.22)
        order.append(None)
    widths.append(1.0)
    order.append(step)

row = st.columns(widths, vertical_alignment="center")
for column, step in zip(row, order):
    if step is None:
        column.markdown(
            "<div style='text-align:center;opacity:.25;font-size:.8rem'>›</div>",
            unsafe_allow_html=True)
        continue

    state = step_state(step)
    number = "✓" if state == "done" else str(step["n"] + 1)
    title = step["title"]
    label = f"{number} {title}" if state == "now" else (
        f":gray[{number} {title}]" if state == "wait" else f"{number} {title}")
    if column.button(label, key=f"nav{step['n']}", width="stretch",
                     type="primary" if state == "now" else "tertiary"):
        go(step["n"])

# Подпись под лентой отвечает на три вопроса сразу: где мы, сколько сделано
# и что из оставшегося можно не делать.
here = STEPS[step_now]
info_here = by_key.get(here["key"]) if here["key"] else None
line = f"Шаг {step_now + 1} из {len(STEPS)} · {here['title']}"
if info_here and info_here["count"]:
    line += f" · введено {info_here['count']}"
line += f" · всего заполнено {done_count} из {total_required}"
st.caption(line)
st.divider()


def step_footer(hint: str = "") -> None:
    """Кнопки «Назад» и «Дальше» — тем же порядком на каждом шаге."""
    st.divider()
    if hint:
        st.caption(hint)
    back, forward = st.columns(2)
    if step_now > 0 and back.button("Назад", width="stretch",
                                    icon=":material/arrow_back:"):
        go(step_now - 1)
    if step_now < LAST_STEP and forward.button(
            "Дальше", type="primary", width="stretch",
            icon=":material/arrow_forward:"):
        go(step_now + 1)


def on(n: int) -> bool:
    """Рисуется ли сейчас этот шаг."""
    return step_now == n


# Порядок шагов на экране отличается от порядка блоков в коде, поэтому
# каждый блок сам говорит, каким шагом он показывается.
#   блок в коде → шаг на экране
#   0 классы → 1     3 кабинеты → 2    1 предметы → 3    2 учителя → 4
#   4 нагрузка → 5   5 пожелания → 6   6 план и 7 нормы → 7    8 составить → 8
tabs = {0: on(1), 1: on(3), 2: on(4), 3: on(2), 4: on(5),
        5: on(6), 6: on(7), 7: on(7), 8: on(8)}


def show_assignment() -> None:
    """Быстрый ввод нагрузки: предмет → учитель → его классы.

    Построчный ввод для городской школы невозможен: 500 строк, где класс,
    предмет и часы УЖЕ известны из типового плана, а вписать надо только,
    кто ведёт. Здесь то же самое делается наоборот — выбираем предмет
    и раздаём его классы учителям пачками. Математика на 28 классов —
    это 7 учителей вместо 28 строк.
    """
    load = tables["load"]
    names = options_of("teachers", "ФИО")
    if not len(load):
        st.info("Сначала добавьте строки нагрузки — кнопкой ниже, в полной таблице, "
                "или мастером первого запуска.", icon=":material/info:")
        return
    if not names:
        st.warning("Сначала заведите учителей на вкладке «3. Учителя».",
                   icon=":material/person_off:")
        return

    progress = subject_progress(load)
    done = int(progress["назначено"].sum())
    total = int(progress["мест"].sum())
    st.progress(done / total if total else 0.0,
                text=f"Назначено {done} мест из {total}")

    # Предметы, где ещё есть пустые места, — первыми: с них и надо начинать.
    def title(row) -> str:
        left = int(row["мест"]) - int(row["назначено"])
        return f"{row['предмет']} — осталось {left}" if left else f"{row['предмет']} ✓"

    labels = {title(row): row["предмет"] for _, row in progress.iterrows()}
    picked = st.selectbox("Предмет", list(labels), key="assign_subject")
    subject = labels[picked]

    slots = subject_slots(load, subject)
    divided = subject in split_subjects(load)
    if divided:
        st.caption("Предмет с делением: у каждого класса два места — «(1)» и «(2)». "
                   "Их обязаны вести РАЗНЫЕ учителя: подгруппы занимаются одновременно.")
    st.caption("Класс с подписью — уже за кем-то. Выберете его — он перейдёт "
               "к новому учителю, у прежнего пропадёт.")

    # Отпечаток текущей раскладки предмета. Он входит в ключи виджетов, потому
    # что Streamlit, увидев ключ в session_state, ИГНОРИРУЕТ новое значение
    # default — и список продолжал показывать прежний выбор даже после того,
    # как данные изменились. Из-за этого назначение свежезаведённого класса
    # молча терялось. Меняются данные — меняется ключ — виджет строится заново.
    stamp = abs(hash(tuple(f"{r['метка']}:{r['учитель']}" for _, r in slots.iterrows()))) % 10**8

    hours = teacher_hours(load)
    busy = {teacher: sum(int(r["часов"]) for _, r in slots.iterrows()
                         if r["учитель"] == teacher)
            for teacher in slots["учитель"].unique() if teacher}

    # Учителя, уже ведущие предмет, плюс одна пустая строка на нового.
    # Порядок алфавитный и ключи виджетов — по ИМЕНИ, а не по номеру строки.
    # С номерами был баг: стоило передать класс другому, как порядок учителей
    # менялся, значения виджетов доставались соседям и назначения слетали
    # пачками (потеряно 11 классов на проверке 24.08.2026).
    current = sorted({teacher for teacher in slots["учитель"] if teacher})
    st.markdown("**Кто ведёт предмет**")
    for teacher in current + [""]:
        slug = teacher or "new"
        columns = st.columns([2, 5])
        who = columns[0].selectbox(
            "Учитель", [""] + names,
            index=(names.index(teacher) + 1) if teacher in names else 0,
            key=f"who_{subject}_{slug}_{stamp}", label_visibility="collapsed",
            placeholder="Добавить учителя…")
        # В списке ВСЕ классы школы, а не только те, где предмет уже заведён.
        # Два разных списка («раздать существующее» отдельно, «добавить класс»
        # отдельно) — искусственное деление: завуч ищет класс там, где выбирает
        # учителя, и не обязан знать, есть ли строка в таблице нагрузки.
        #   • место занято другим — подписано хозяином, выбор забирает его себе;
        #   • места ещё нет      — помечено «+ завести», выбор создаёт строку.
        options, label_of, mine, fresh = [], {}, [], {}
        for _, row in slots.iterrows():
            owner = row["учитель"]
            text = row["метка"] if (not owner or owner == teacher) \
                else f"{row['метка']} · {owner}"
            options.append(text)
            label_of[text] = row["метка"]
            if owner and owner == teacher:
                mine.append(text)
        for class_name in options_of("classes", "класс"):
            if class_name in set(slots["класс"]):
                continue
            text = f"{class_name} · + завести"
            options.append(text)
            fresh[text] = class_name
        chosen = columns[1].multiselect(
            "Классы", options, default=mine, key=f"cls_{subject}_{slug}_{stamp}",
            label_visibility="collapsed",
            placeholder="Классы этого учителя по предмету…")
        if who and (set(chosen) != set(mine) or (teacher and who != teacher)):
            updated = tables["load"]

            # Сначала заводим места там, где предмета ещё не было, иначе
            # назначать нечего: учитель привязывается к строке нагрузки.
            new_classes = [fresh[text] for text in chosen if text in fresh]
            skipped: list[str] = []
            if new_classes:
                updated, skipped = add_subject_slots(
                    updated, subject, new_classes,
                    hours=st.session_state.get(f"newh_{subject}") or None)

            picked = [label_of[text] for text in chosen if text in label_of]
            for class_name in new_classes:
                if class_name in skipped:
                    continue
                picked += [slot_label(class_name, part)
                           for part in (("1", "2") if divided else ("",))]

            if teacher and who != teacher:
                updated = assign_teacher(updated, subject, teacher, [])
            updated = assign_teacher(updated, subject, who, picked)

            # Перерисовка — ТОЛЬКО если данные правда изменились. Иначе выбор
            # класса, который не удалось завести (план молчит про часы),
            # запускал перезапуск снова и снова: страница мигала, а причина
            # так и не показывалась — до неё не доходило выполнение.
            if not updated.equals(tables["load"]):
                tables["load"] = updated
                save_tables(tables, settings, st.session_state.wishes)
                st.rerun()
            if skipped:
                st.warning(
                    "Типовой план не задаёт часы предмета «" + subject + "» для: "
                    + ", ".join(skipped)
                    + ". Укажите, сколько часов в неделю, — и класс заведётся.",
                    icon=":material/warning:")
                st.number_input("Часов в неделю для новых классов", 0, 12, 0,
                                key=f"newh_{subject}")
        if who:
            total_hours = hours.get(who, 0)
            here = busy.get(who, 0)
            columns[0].caption(f"{total_hours} ч всего · {here} ч по предмету")

    left = [r["метка"] for _, r in slots.iterrows() if not r["учитель"]]
    if left:
        st.warning("Без учителя: " + ", ".join(left[:20])
                   + ("…" if len(left) > 20 else ""), icon=":material/warning:")

        # Автораздача — черновик: разложить оставшееся по часам поровну,
        # а потом поправить руками пару строк. Кто именно ведёт 7«Б», знает
        # только школа, но раскладывать 28 классов по одному — полчаса кликов.
        pool = st.multiselect(
            "Раздать оставшиеся классы между учителями",
            names, default=current, key=f"pool_{subject}",
            placeholder="Выберите, между кем делить…",
            help="Система разложит незакрытые классы так, чтобы часы у этих "
                 "учителей вышли примерно поровну. Подгруппы одного класса "
                 "достанутся разным людям — они занимаются одновременно.")
        if pool and st.button("Разложить поровну", key=f"spread_{subject}",
                              icon=":material/shuffle:"):
            tables["load"] = spread_evenly(tables["load"], subject, pool)
            save_tables(tables, settings, st.session_state.wishes)
            st.rerun()
    else:
        st.success("Все классы этого предмета закрыты.", icon=":material/check:")

    heavy = {who: total for who, total in hours.items() if total > 30}
    if heavy:
        st.caption("Больше 30 часов в неделю: "
                   + ", ".join(f"{who} — {total} ч" for who, total in sorted(heavy.items()))
                   + ". Проверьте: это выше полутора ставок.")


def task_fingerprint(school, weights, rules, budget: int) -> str:
    """Отпечаток задачи: данные школы плюс настройки поиска.

    Нужен, чтобы не считать заново то, что уже посчитано. Составление —
    это минуты работы процессора, а кнопку «Составить» нажимают часто:
    посмотреть результат, вернуться, нажать снова. В облаке за такие
    повторы платформа урезает приложению процессор.

    В отпечаток входит ВСЁ, что меняет результат: нагрузка, кабинеты,
    пожелания, веса, строгость норм, бюджет времени. Меняется что угодно
    из этого — считаем заново, иначе показываем готовое.
    """
    payload = {
        "load": [(i.group_id, i.subject_id, i.teacher_id, i.hours_per_week,
                  i.kind.value, i.level.value, i.room_id,
                  i.room_kind.value if i.room_kind else None) for i in school.load],
        "rooms": [(r.id, r.kind.value) for r in school.rooms],
        "teachers": [(t.id, sorted(str(x) for x in t.unavailable),
                      sorted(str(x) for x in t.disliked), t.method_day)
                     for t in school.teachers],
        "classes": [(c.id, c.parallel, c.shift.value, c.advanced) for c in school.classes],
        "periods": school.periods_per_day,
        "days": sorted(d for d, kind in school.day_kinds.items()
                       if kind.value == "lessons"),
        "weights": weights.__dict__,
        "rules": rules.__dict__,
        "budget": budget,
    }
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def show_diagnosis(lines: list[str]) -> None:
    """Показать разбор причин.

    Разбор отдаёт готовый текст с разметкой: жирным — название узкого места,
    строками с «•» — перечисления внутри него. Свои маркеры дописывать поверх
    нельзя, иначе получаются точки внутри точек. Название узкого места
    отбивается сверху, чтобы несколько причин читались как отдельные блоки,
    а не как один сплошной список.
    """
    for line in lines:
        if not line:
            continue
        if line.startswith("**"):
            st.markdown("")
            st.markdown(line)
        elif line.startswith("•"):
            st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;{line}", unsafe_allow_html=True)
        else:
            st.markdown(line)


@st.fragment(run_every="1s")
def show_progress(job, budget: int) -> None:
    """Экран составления: что уже улучшилось и сколько ещё можно улучшить.

    Обычного прогресс-бара «осталось три минуты» тут быть не может: солвер
    либо доказывает оптимальность и останавливается сам, либо работает до конца
    бюджета. Поэтому показываем две честные величины — потраченное время
    и `gap`: насколько текущее расписание ещё может стать лучше.

    Фрагмент перерисовывается раз в секунду сам по себе, не трогая остальную
    страницу, — поэтому кнопка «Остановить» живая, пока идёт поиск.
    """
    latest = job.latest
    spent = job.seconds()

    if latest is None or latest.stage == "search":
        st.info("Ищу первое законное расписание — то, где никто не оказался "
                "в двух местах сразу.", icon=":material/search:")
    else:
        st.success("Законное расписание уже есть. Дальше улучшаю: убираю окна "
                   "и выравниваю дни.", icon=":material/check_circle:")

    st.progress(min(1.0, spent / max(1, budget)),
                text=f"{spent:.0f} с из {budget} с")

    if latest and latest.metrics:
        first = job.first_improved
        columns = st.columns(len(latest.metrics))
        for column, (label, value) in zip(columns, latest.metrics.items()):
            was = (first.metrics if first else {}).get(label)
            delta = None if was is None or was == value else value - was
            column.metric(label, value, delta=delta, delta_color="inverse")

    line = []
    scored = job.first_scored
    if latest and scored and scored.penalty and latest.penalty is not None:
        better = (scored.penalty - latest.penalty) / scored.penalty * 100
        line.append(f"Расписание стало лучше на **{better:.0f}%** с первой версии")
    if latest:
        line.append(f"улучшений найдено: **{latest.solutions}**")
    if line:
        st.caption(" · ".join(line) + ". Поиск останавливается сам, если "
                   "доказано, что лучше уже не будет.")
    if latest and latest.gap is not None:
        st.caption(f"Теоретический запас улучшения — {latest.gap * 100:.0f}%. "
                   "Это верхняя оценка, а не обещание: обычно она остаётся "
                   "большой, даже когда расписание уже хорошее.")

    # График падения штрафа: видно, вышел ли поиск на полку — тогда ждать
    # дальше смысла мало и можно забирать расписание.
    points = [(p.seconds, p.penalty) for p in job.history if p.penalty is not None]
    if len(points) > 2:
        st.line_chart(pd.DataFrame(points, columns=["секунды", "штраф"]).set_index("секунды"),
                      height=180)

    if job.stop_requested:
        st.caption("Останавливаю — заберу лучшее из найденного…")
    elif st.button("Остановить и взять текущее", icon=":material/stop_circle:"):
        job.request_stop()

    if not job.running:
        st.rerun()


def explain(key: str) -> None:
    """Шапка шага: где мы, что здесь делаем и зачем.

    Заголовок с номером повторяет то, что показывает лента, — и это не
    избыточность: лента вверху, а работа идёт здесь, и человек должен видеть
    название шага там, где смотрит.
    """
    step = by_key[key]
    place = next((s for s in STEPS if s["key"] == key), None)
    if place:
        # Счётчик стоит здесь, а не в ленте: в ленте он ломал вёрстку, а тут
        # для него есть место и он к месту — человек видит, сколько уже завёл,
        # ровно там, где заводит.
        title = f"Шаг {place['n'] + 1}. {place['title']}"
        if step["count"]:
            title += f" — {step['count']}"
        st.subheader(title)
    st.caption(step["why"])
    if step["blocked_by"]:
        st.warning("Сначала заполните: " + ", ".join(step["blocked_by"]) + ". " + step["empty"])
    elif not step["done"]:
        st.caption("Пока пусто. " + step["empty"])


def options_of(table: str, column: str) -> list[str]:
    """Значения для выпадающего списка — из уже введённых таблиц."""
    values = tables.get(table)
    if values is None or column not in values:
        return []
    return [str(v).strip() for v in values[column] if str(v).strip() and str(v) != "nan"]


# ------------------------------------------------------------------ шаг 0: школа
if on(0):
    st.subheader("Шаг 1. Школа")
    st.caption("Сначала рамка, в которую всё уложится: сколько уроков помещается "
               "в день и сколько дней в неделе идут уроки. От этого зависит "
               "предельная нагрузка классов и всё дальнейшее.")

    settings["name"] = st.text_input(
        "Название школы", settings.get("name", ""),
        placeholder="Средняя школа № 1 г. Барановичи",
        help="Попадёт в заголовок расписания.")

    left, right = st.columns(2)
    settings["periods"] = left.number_input(
        "Максимум уроков в день", 4, 10, int(settings.get("periods", 8)),
        help="Насколько высокой может быть сетка. Это не значит, что уроков будет "
             "столько: система ставит ровно то, что есть в нагрузке. Прямой нормы "
             "на это число нет ни в одном документе — оно ограничено недельной "
             "нагрузкой и временем окончания смены.")
    settings["days"] = right.number_input(
        "Дней с уроками", 4, 6, int(settings.get("days", 5)),
        help="В Беларуси учебная неделя пятидневная (п. 87 СанПиН № 206).")
    settings["sixth_day"] = st.checkbox(
        "Шестой школьный день: суббота с факультативами и кружками, уроков нет",
        settings.get("sixth_day", True))

    # Весь путь целиком — один раз, в начале. Человек должен понимать, во что
    # ввязывается: сколько шагов, что на каждом и где длинный участок.
    with st.expander("Что предстоит заполнить — весь путь", expanded=True):
        st.markdown("""
| Шаг | Что вводим | Сколько это |
|---|---|---|
| **2. Классы** | какие классы есть в школе | минуты |
| **3. Кабинеты** | номера и типы кабинетов | минуты, **сразу покажет, хватает ли их** |
| **4. Предметы** | берутся кнопкой из типового плана | секунды |
| **5. Учителя** | фамилии; остальное по желанию | минут десять |
| **6. Нагрузка** | кто какой предмет ведёт | **самый долгий шаг** |
| 7. Пожелания | когда учитель не может работать | по желанию |
| 8. Проверка | сверка с планом и нормы | обычно ничего не трогают |
| **9. Составить** | результат | минуты ожидания |
""")
        st.caption("Часы, предметы и черновик нагрузки система знает из типового "
                   "учебного плана — вписывать вручную нужно в основном то, "
                   "кто какой класс ведёт. Введённое сохраняется само, "
                   "но файл со школой лучше скачать себе — кнопка слева.")

    step_footer("Дальше — классы. Их можно задать по параллелям, "
                "литеры проставятся сами.")


# ------------------------------------------------------------------ шаг 1: классы
if tabs[0]:
    explain("classes")

    # Заводить два десятка классов по одному — работа ни о чём: литеры идут
    # подряд, и система расставит их сама. Поэтому сначала быстрый способ,
    # а таблица ниже — чтобы поправить частности.
    if not len(tables["classes"]):
        st.markdown("**Сколько классов в каждой параллели**")
        counts, sizes = {}, {}
        columns = st.columns(7)
        for n, parallel in enumerate(range(5, 12)):
            with columns[n]:
                st.markdown(f"**{parallel}-е**")
                counts[parallel] = st.number_input(
                    "классов", 0, 10, 0, key=f"q_cnt{parallel}",
                    label_visibility="collapsed")
                sizes[parallel] = st.number_input(
                    "учеников", 0, 40, 24, key=f"q_sz{parallel}",
                    label_visibility="collapsed")
        st.caption("Верхнее поле — сколько классов в параллели, нижнее — "
                   "сколько в них учеников. Литеры (А, Б, В) проставятся сами.")
        if any(counts.values()):
            preview = generate_classes(counts, sizes)
            st.success(f"Будет заведено {len(preview)} классов: "
                       + ", ".join(preview["класс"].tolist()[:12])
                       + ("…" if len(preview) > 12 else ""))
            if st.button("Завести эти классы", type="primary", width="stretch",
                         icon=":material/playlist_add:"):
                tables["classes"] = preview
                save_tables(tables, settings, st.session_state.wishes)
                st.rerun()
        st.divider()

    st.caption("Пишите так, как класс называется в школе: 5А, 10Б. «Повышенный уровень» "
               "ставить не нужно — он проставится сам, если на шаге «Нагрузка» "
               "у предмета выбран повышенный уровень.")
    tables["classes"] = st.data_editor(
        tables["classes"], num_rows="dynamic", width="stretch",
        column_order=[c for c in tables["classes"].columns if c != "параллель"],
        column_config={
            "класс": st.column_config.TextColumn(required=True, help="Например: 7Б"),
            "учеников": st.column_config.NumberColumn(min_value=0, max_value=40),
            "повышенный уровень": st.column_config.CheckboxColumn(
                help="Проставляется автоматически по уровню предметов в нагрузке."),
        })

    step_footer('Дальше — кабинеты. Там сразу станет видно, хватает ли их на все классы.')

if tabs[1]:
    explain("subjects")
    st.caption("Предмету, которому нужен особый кабинет, выберите тип. Всем остальным — "
               "«обычный»: это значит любой свободный учебный кабинет. Галочка "
               "«только в нём» — для тех, кого без своего кабинета не провести: "
               "физкультура, информатика, труд. У физики, химии и биологии её "
               "обычно не ставят: в свой кабинет они идут на лабораторную, "
               "а в остальное время занимают обычный класс.")
    if st.button("Взять предметы из типового плана", key="add_subjects", icon=":material/add:"):
        suggested = generate_subjects(parallels_of(tables["classes"]))
        have = set(options_of("subjects", "предмет"))
        add = suggested[~suggested["предмет"].isin(have)]
        if len(add):
            tables["subjects"] = pd.concat([tables["subjects"], add], ignore_index=True)
            st.success(f"Добавлено предметов: {len(add)}")
        else:
            st.info("Все предметы типового плана уже заведены.")
    tables["subjects"] = st.data_editor(
        tables["subjects"], num_rows="dynamic", width="stretch",
        column_config={
            "предмет": st.column_config.TextColumn(required=True),
            "кабинет": st.column_config.SelectboxColumn(options=list(ROOM_KINDS)),
            "только в нём": st.column_config.CheckboxColumn(
                help="Урок нельзя провести нигде, кроме этого кабинета. Снимите "
                     "галочку, если предмет может идти и в обычном классе — "
                     "тогда система посадит в спецкабинет тех, кому он нужнее, "
                     "а остальные пойдут в свободные комнаты."),
            "всегда парой": st.column_config.CheckboxColumn(
                help="Предмет ставится только двумя уроками подряд. Так обычно "
                     "идёт трудовое обучение: пока класс дойдёт до мастерской "
                     "и переоденется, одного урока не остаётся."),
        })

    step_footer('Дальше — учителя. Нужны только фамилии, остальное по желанию.')

if tabs[2]:
    explain("teachers")
    st.caption("Заполнять обязательно только ФИО. Методический день — цифра 1–5 "
               "(1 = понедельник), если у учителя есть день без уроков. Свой кабинет — "
               "при кабинетной системе: уроки будут ставиться туда. «Уроков в день» — "
               "потолок нагрузки: система собирает уроки учителя плотнее, чтобы он "
               "реже ездил в школу, и без потолка может выдать восемь подряд.")
    tables["teachers"] = st.data_editor(
        tables["teachers"], num_rows="dynamic", width="stretch",
        column_config={
            "ФИО": st.column_config.TextColumn(required=True, help="Например: Иванова И. И."),
            "методический день": st.column_config.TextColumn(help="1–5, или пусто"),
            "свой кабинет": st.column_config.SelectboxColumn(
                options=[NONE_CHOICE] + options_of("rooms", "кабинет"), required=False),
            "уроков в день": st.column_config.TextColumn(
                help="Больше этого числа уроков в один день не поставится. "
                     "Пусто — ограничения нет."),
            "совместитель": st.column_config.CheckboxColumn(
                help="Работает ещё в одной школе. Система пока не знает его "
                     "расписания там и считает свободным — отметьте дни, когда "
                     "он у нас не бывает, на вкладке «6. Пожелания»."),
        })

    step_footer('Дальше — нагрузка. Это самый долгий шаг: кто какой предмет ведёт.')

if tabs[3]:
    explain("rooms")

    if not len(tables["rooms"]):
        st.markdown("**Сколько кабинетов какого типа**")
        regular = st.number_input("Обычных учебных кабинетов", 0, 60, 12,
                                  key="q_regular",
                                  help="Их должно быть не меньше, чем классов: "
                                       "на первом уроке заняты все классы сразу.")
        special = {}
        columns = st.columns(4)
        for n, kind in enumerate(["физика", "химия", "биология", "компьютерный",
                                  "спортзал", "мастерская (техтруд)",
                                  "мастерская (обсл. труд)", "актовый зал"]):
            with columns[n % 4]:
                special[kind] = st.number_input(kind, 0, 10, 1 if n < 6 else 0,
                                                key=f"q_rm{n}")
        if st.button("Завести эти кабинеты", type="primary", width="stretch",
                     icon=":material/playlist_add:"):
            tables["rooms"] = generate_rooms(
                regular, {k: v for k, v in special.items() if v})
            save_tables(tables, settings, st.session_state.wishes)
            st.rerun()
        st.divider()
    st.caption("Каждый кабинет — отдельной строкой. Колонка «классов сразу» нужна "
               "спортзалу: там обычно занимаются два класса одновременно, каждый "
               "со своим учителем. У обычного кабинета оставьте единицу.")
    tables["rooms"] = st.data_editor(
        tables["rooms"], num_rows="dynamic", width="stretch",
        column_config={
            "кабинет": st.column_config.TextColumn(required=True),
            "тип": st.column_config.SelectboxColumn(options=list(ROOM_KINDS)),
            "мест": st.column_config.NumberColumn(min_value=0, max_value=60,
                                                  help="Сколько учеников помещается."),
            "классов сразу": st.column_config.NumberColumn(
                min_value=1, max_value=4,
                help="Сколько классов занимается здесь ОДНОВРЕМЕННО. Спортзал — "
                     "обычно 2. Без этого школа с одним залом не описывается: "
                     "24 класса по 3 часа физкультуры дают 72 урока в неделю, "
                     "а пятидневка вмещает 40."),
        })

    # Сразу, не дожидаясь нагрузки. Классов и кабинетов достаточно, чтобы
    # сказать главное: хватит ли комнат вообще. Ждать с этим до конца ввода
    # нельзя — на школу в 24 класса нагрузка вводится часами, и узнать
    # в конце, что расписания не существует, значит потерять эти часы зря.
    for line in rooms_verdict(tables):
        st.warning(line, icon=":material/priority_high:")

    step_footer('Дальше — предметы. Их можно набрать одной кнопкой из типового плана.')

if tabs[4]:
    explain("load")
    st.caption("Класс, предмет и часы система знает из типового плана. Вручную нужно "
               "только одно: кто ведёт. Для этого есть быстрый режим — он ниже.")

    mode = st.segmented_control(
        "Режим", ["Назначить учителей", "Полная таблица"],
        default="Назначить учителей", key="load_mode", label_visibility="collapsed")

    if mode == "Назначить учителей":
        show_assignment()

    if mode == "Полная таблица":
        with st.expander("Что означают остальные колонки"):
            st.markdown(
                "**Подгруппа** — заполняется только при делении класса (иностранный, "
                "труд, информатика). Заведите две строки, в одной напишите «1», "
                "в другой «2»: система поставит их в один слот, и половина класса "
                "не будет ждать вторую.\n\n"
                "**Уровень** — базовый или повышенный. В X–XI это меняет часы: "
                "математика 4 или 6, физика 2 или 4. Класс с повышенным уровнем "
                "считается профильным, и предельная недельная нагрузка для него "
                "другая.\n\n"
                "**Тип** — урок, факультатив, стимулирующее занятие или классный час. "
                "Факультативы тоже занимают учителя и кабинет, поэтому их стоит "
                "вносить.\n\n"
                "**Кабинет** — только для делений, где подгруппы расходятся по разным "
                "кабинетам: труд у мальчиков в мастерской, у девочек в кабинете "
                "обслуживающего труда. В остальных случаях оставьте пустым."
            )
        if st.button("Добавить недостающие строки по типовому плану", icon=":material/add:"):
            draft, unknown = generate_load(tables["classes"])
            existing = {(str(r["класс"]), str(r["предмет"]), str(r.get("подгруппа") or ""))
                        for _, r in tables["load"].iterrows()}
            add = [r for _, r in draft.iterrows()
                   if (str(r["класс"]), str(r["предмет"]), str(r["подгруппа"])) not in existing]
            if add:
                tables["load"] = pd.concat([tables["load"], pd.DataFrame(add)], ignore_index=True)
                st.success(f"Добавлено строк: {len(add)}. Осталось вписать учителей.")
                if unknown:
                    st.warning("Часы этих предметов в типовом плане заданы дробью по полугодиям — "
                               "впишите сами: " + "; ".join(unknown[:6]))
            else:
                st.info("Всё, что есть в типовом плане, уже заведено.")

        tables["load"] = st.data_editor(
        tables["load"], num_rows="dynamic", width="stretch",
        column_config={
            "класс": st.column_config.SelectboxColumn(options=options_of("classes", "класс"),
                                                     required=True),
            "предмет": st.column_config.SelectboxColumn(options=options_of("subjects", "предмет"),
                                                       required=True),
            "учитель": st.column_config.SelectboxColumn(options=options_of("teachers", "ФИО"),
                                                       required=True),
            "часов": st.column_config.NumberColumn(min_value=0, max_value=12, required=True),
            "подгруппа": st.column_config.TextColumn(help="«1» и «2» при делении, иначе пусто"),
            "уровень": st.column_config.SelectboxColumn(options=list(LEVELS), required=False),
            "тип": st.column_config.SelectboxColumn(options=list(LESSON_KINDS), required=False),
            "кабинет": st.column_config.SelectboxColumn(
                options=[NONE_CHOICE] + list(ROOM_KINDS), required=False),
        })

        step_footer('Дальше — пожелания учителей. Шаг необязательный, можно пропустить.')

if tabs[5]:
    explain("wishes")
    names = options_of("teachers", "ФИО")
    if not names:
        st.info("Сначала заведите учителей на вкладке «3. Учителя».")
    else:
        # Раньше селектор и легенда стояли двумя колонками и не совпадали
        # по верхнему краю — глаз спотыкался на каждой перерисовке.
        who = st.selectbox("Учитель", names, width=340)
        st.markdown(
            f"**{CANT}** — жёсткий запрет: урок сюда не встанет никогда.  \n"
            f"**{DISLIKE}** — пожелание: система поставит, только если иначе расписание "
            "не сходится, и постарается не ставить."
        )
        st.caption("Осторожно с запретами: если их слишком много, расписания может "
                   "не существовать вовсе. Всё, что обсуждаемо, лучше отмечать как "
                   "«нежелательно».")
        days = int(settings.get("days", 5))
        periods = int(settings.get("periods", 8))
        grid = wishes_to_grid(st.session_state.wishes.get(who, {}), days, periods)
        edited = st.data_editor(
            grid, width="stretch",
            column_config={c: st.column_config.SelectboxColumn(f"урок {c}", options=WISH_OPTIONS,
                                                              width="small")
                           for c in grid.columns})
        st.session_state.wishes[who] = grid_to_wishes(edited)

        filled = {n: w for n, w in st.session_state.wishes.items()
                  if w.get("hard") or w.get("soft")}
        if filled:
            st.caption("Уже заполнено: " + ", ".join(
                f"{n} ({len(w.get('hard', []))} запретов, {len(w.get('soft', []))} пожеланий)"
                for n, w in filled.items()))

    step_footer('Дальше — проверка: сверка с учебным планом и санитарные нормы.')

if tabs[6]:
    st.subheader("Шаг 8. Проверка")
    st.caption("Два вопроса перед составлением: всё ли есть по учебному плану "
               "и какие санитарные нормы применять. Оба можно оставить как есть.")
    st.markdown("**Что положено классам по учебному плану**")
    st.caption("Сверка введённой нагрузки с типовым учебным планом (постановление "
               "Минобразования № 75). Без неё забытый предмет обнаружится в сентябре: "
               "солвер составит расписание из того, что дали, и промолчит.")

    school_now, _ = build_school(tables, settings, st.session_state.wishes)
    summary = plan_summary(school_now)
    st.dataframe(summary, width="stretch", hide_index=True)

    detail = compare_with_plan(school_now)
    issues = detail[detail["статус"] != "✓"]
    if len(issues):
        st.warning(f"Расхождений с планом: {len(issues)}")
        st.dataframe(issues, width="stretch", hide_index=True)
    else:
        st.success("Нагрузка совпадает с типовым учебным планом по всем классам.")

    with st.expander("Полная сверка по всем предметам"):
        st.dataframe(detail, width="stretch", hide_index=True)

    st.divider()
    st.markdown("**Профиль класса (X–XI)**")
    st.caption("Профиль — это набор предметов на повышенном уровне. Типовой план "
               "задаёт их часы диапазоном: математика «4–6», где 4 — базовый уровень, "
               "6 — повышенный. Какие предметы профильные, решает школа.")
    profiles = {k: v for k, v in (load_plan().get("profiles") or {}).items()
                if not k.startswith("_")}
    senior = [c.name for c in school_now.classes if c.parallel >= 10]
    if not senior or not profiles:
        st.caption("Профили применимы к X–XI классам. Таких классов пока нет.")
    else:
        col1, col2 = st.columns(2)
        target = col1.selectbox("Класс", senior)
        profile = col2.selectbox("Профиль", list(profiles))
        st.caption("Предметы профиля: " + ", ".join(profiles[profile]))
        if st.button("Применить профиль", width="stretch"):
            tables["load"], changes = apply_profile(tables["load"], target, profiles[profile])
            for line in changes:
                st.write("• " + line)
            st.success("Готово. Проверьте сверку выше и сохраните данные.")


if tabs[7]:
    st.subheader("Санитарные нормы")
    st.caption("Норма — требование к школе, а не к алгоритму. Если применить всё жёстко "
               "там, где часов больше, чем места, солвер вернёт «решения нет» и ничего "
               "не объяснит. Переключатель даёт выбор: ослабить норму и увидеть "
               "расписание с перечнем нарушений.")
    strictness = {}
    defaults = Rules()
    labels = {v: k for k, v in STRICTNESS.items()}
    for name, title in RULE_TITLES.items():
        current = getattr(defaults, name)
        chosen = st.segmented_control(
            title, list(STRICTNESS), default=labels[current],
            key=f"rule_{name}")
        strictness[name] = STRICTNESS[chosen or labels[current]]
        st.caption(RULE_SOURCES.get(name, ""))
    st.session_state.rules = Rules(**strictness)

    st.divider()
    st.caption("Первоисточники: постановление Минздрава РБ № 206 от 27.12.2012; "
               "постановление Совмина РБ № 525 от 07.08.2019 (ССЭТ) в ред. 12.07.2024; "
               "типовые учебные планы, постановление Минобразования РБ № 75 от 23.04.2025. "
               "Цифры и цитаты — в data/sanpin_by.json.")

    step_footer('Дальше — составление расписания.')

if tabs[8]:
    st.subheader("Шаг 9. Составить расписание")
    school, problems = build_school(tables, settings, st.session_state.wishes)

    cols = st.columns(4)
    cols[0].metric("Классов", len(school.classes))
    cols[1].metric("Учителей", len(school.teachers))
    cols[2].metric("Часов в неделю", sum(i.hours_per_week for i in school.load))
    cols[3].metric("Слотов в сетке", len(school.lesson_slots()))

    scale = school.norms.difficulty_scale
    if scale:
        covered = sum(1 for subj in school.subjects
                      if any(school.norms.difficulty(subj.name, c.parallel)
                             for c in school.classes))
        st.caption(
            f"Нормы загружены: шкала трудности на {len(scale)} предметов, распознано "
            f"в ваших данных — {covered} из {len(school.subjects)}. Урок "
            f"{school.norms.lesson_minutes} мин; предельная недельная нагрузка V–XI: "
            + ", ".join(str(school.norms.max_hours_per_week[p])
                        for p in sorted(school.norms.max_hours_per_week) if p >= 5) + " ч."
        )
    else:
        st.caption("Санитарные нормы не загружены — проверки по нормам выключены.")

    for warning in check_norms(school):
        st.warning(warning, icon=":material/warning:")

    if problems:
        st.error("Данные не сойдутся — сначала исправьте:")
        for p in problems:
            st.write("• " + p)

    rules = st.session_state.get("rules", Rules())
    job = st.session_state.get("job")

    if job is None:
        # Готовое расписание для ЭТИХ ЖЕ данных — показываем его, а не считаем
        # заново. Отпечаток берёт и данные, и настройки: изменилось что угодно —
        # кнопка снова предлагает составить.
        fingerprint = task_fingerprint(school, weights, rules, budget)
        done = st.session_state.get("done_for")

        if done == fingerprint and st.session_state.get("result_view"):
            st.success("Расписание для этих данных уже составлено — оно ниже. "
                       "Изменится хоть что-то во вводе или настройках — "
                       "система предложит пересчитать.", icon=":material/check:")
            if st.button("Составить заново", width="stretch",
                         icon=":material/refresh:",
                         help="Поиск идёт разными путями, поэтому второй раз "
                              "может выйти удачнее. Но чаще это просто трата времени."):
                st.session_state.pop("done_for", None)
                st.session_state.job = SolveJob(school, max_seconds=budget,
                                                weights=weights, rules=rules)
                st.session_state.job.start()
                st.rerun()
        elif st.button("Составить расписание", type="primary", disabled=bool(problems),
                       width="stretch", icon=":material/play_arrow:"):
            # Солвер уезжает в поток: иначе страница замирает на все десять
            # минут — ни прогресса, ни возможности прервать (см. lad/job.py).
            st.session_state.job = SolveJob(school, max_seconds=budget,
                                            weights=weights, rules=rules)
            st.session_state.job.start()
            st.rerun()

    if job is not None and job.running:
        show_progress(job, budget)
        st.stop()

    if job is not None and job.finished:
        if job.error is not None:
            st.error(f"Составление прервалось ошибкой: {job.error}")
            st.stop()
        result, elapsed = job.result, job.elapsed

        if not result.ok:
            # Два разных ответа солвера, которые нельзя валить в один.
            #   INFEASIBLE — доказано, что расписания не существует. Виноваты
            #                данные или нормы, и есть смысл разбираться.
            #   UNKNOWN    — не успел за отведённое время. Расписание, возможно,
            #                есть; на 28 классах поиск занимает около двух минут.
            # Раньше оба показывались как «решения нет», и завуч на коротком
            # бюджете читал разбор про нормы, хотя виновато было время.
            if result.status == "UNKNOWN":
                st.warning(
                    f"За {elapsed:.0f} с законное расписание найти не успели. "
                    "Это не значит, что его нет: на школе в 28 классов поиск "
                    "занимает около двух минут, и чем строже нормы, тем дольше. "
                    "Увеличьте время слева и запустите ещё раз.",
                    icon=":material/hourglass_empty:")
                # Ждать дольше — не единственный выход, и часто не тот.
                # Поиск ПЕРВОГО решения и доказательство того, что решения нет, —
                # разные режимы работы солвера: гимназия в 28 классов молчала
                # семь минут, а невыполнимость из-за нехватки кабинетов
                # доказывалась за семь секунд. Поэтому разбор предлагается
                # наравне с «подождать ещё», а не после.
                longer, why = st.columns(2)
                if budget < 900 and longer.button("Искать дольше", type="primary",
                                                  width="stretch",
                                                  icon=":material/more_time:"):
                    st.session_state.job = SolveJob(school, max_seconds=budget * 2,
                                                    weights=weights, rules=rules)
                    st.session_state.job.start()
                    st.rerun()
                if why.button("Разобраться, почему", width="stretch",
                              icon=":material/troubleshoot:"):
                    with st.spinner("Проверяю по очереди: кабинеты, нормы, данные…"):
                        show_diagnosis(diagnose(school, rules=rules,
                                                max_seconds=min(40, budget),
                                                total_seconds=180))
            else:
                st.error("Такого расписания не существует — солвер это доказал. "
                         "Разбираюсь, что именно мешает…")
                with st.spinner("Снимаю требования по одному и смотрю, какое мешает…"):
                    show_diagnosis(diagnose(school, rules=rules,
                                            max_seconds=min(40, budget),
                                            total_seconds=180))
        else:
            # Готовое расписание собирается ОДИН раз и лежит в состоянии сессии.
            # Иначе каждое скачивание файла (а это перезапуск скрипта) пересчитывало
            # бы отчёт и перерисовывало HTML заново — и, что хуже, экран
            # с результатом исчезал после первого же нажатия «Excel».
            if st.session_state.get("result_of") is not job:
                assign_rooms(school, result.lessons)
                OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
                html = render(school, result.lessons, minutes_spent=elapsed / 60)
                OUT_HTML.write_text(html, encoding="utf-8")
                save_schedule("out/schedule.json", school, result.lessons,
                              {"status": result.status, "seconds": elapsed})
                st.session_state.result_of = job
                st.session_state.done_for = task_fingerprint(school, weights, rules, budget)
                st.session_state.result_view = {
                    "report": check(school, result.lessons),
                    "html": html,
                    "excel": excel_bytes(school, result.lessons),
                }
            view = st.session_state.result_view
            report, html = view["report"], view["html"]

            st.success(f"Готово за {elapsed:.0f} с — {len(result.lessons)} уроков "
                       f"({result.status})")

            # По четыре в ряд: восемь метрик в одну строку сжимаются так,
            # что подписи обрезаются многоточием и цифры теряют смысл.
            summary = list(report.summary().items())
            for start in range(0, len(summary), 4):
                for col, (label, value) in zip(st.columns(4), summary[start:start + 4]):
                    col.metric(label, value)

            # Точечные послабления: норму нельзя было выполнить в конкретном
            # классе, и система ослабила её ТОЛЬКО там. Завуч должен узнать
            # об этом от системы, а не от проверяющего.
            for line in getattr(result, "relaxed", []):
                st.warning(line, icon=":material/rule:")

            if report.violations:
                with st.expander(f"Нарушения ({len(report.violations)})"):
                    for v in report.violations:
                        st.write(f"**{v.rule}** — {v.what} · {v.where}")

            XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

            st.markdown("**Забрать расписание**")
            col1, col2 = st.columns(2)
            col1.download_button("Excel — для работы", view["excel"],
                                 file_name="raspisanie.xlsx", mime=XLSX, width="stretch",
                                 icon=":material/table_view:",
                                 help="Четыре листа: по классам, по учителям, по кабинетам "
                                      "и проверка с метриками и списком нарушений.")
            col2.download_button("HTML — переслать и посмотреть", html, icon=":material/language:",
                                 file_name="raspisanie.html", mime="text/html", width="stretch",
                                 help="Один файл, открывается двойным кликом, читается с телефона.")

            st.markdown("**Что-то не устраивает?**")
            st.caption("Пересобрать всё — значит переставить и то, что уже подходит. "
                       "Выберите классы, которые нужно переделать: остальные уроки "
                       "останутся ровно там, где стоят.")
            redo = st.multiselect(
                "Классы для пересборки", [c.name for c in school.classes],
                key="redo_classes", label_visibility="collapsed",
                placeholder="Какие классы переделать…")

            again, fresh_start = st.columns(2)
            if redo and again.button("Пересобрать выбранное", type="primary",
                                     width="stretch", icon=":material/autorenew:"):
                keep = [lesson for lesson in result.lessons
                        if not (set(school.group(lesson.group_id).class_ids) & set(redo))]
                st.session_state.job = SolveJob(school, max_seconds=budget,
                                                weights=weights, rules=rules, pinned=keep)
                st.session_state.job.start()
                for stale in ("result_of", "result_view"):
                    st.session_state.pop(stale, None)
                st.rerun()
            if fresh_start.button("Составить с нуля", width="stretch",
                                  icon=":material/refresh:"):
                for stale in ("job", "result_of", "result_view", "redo_classes",
                              "done_for"):
                    st.session_state.pop(stale, None)
                st.rerun()

            # Предпросмотр — через iframe, а не st.html: расписание несёт свои
            # стили, и в общем документе они бы протекли на всё приложение.
            # (st.components.v1.html объявлен устаревшим.)
            st.iframe(OUT_HTML, height=700)




if on(LAST_STEP):
    step_footer()

# ------------------------------------------------------------------ автосохранение
# Завуч вводит школу часами. Ручная кнопка «Сохранить» этого не выдерживает:
# закрытая вкладка, перезапуск, случайное обновление страницы — и работа
# пропала. Streamlit выполняет скрипт заново при каждом действии, поэтому
# самое надёжное место для записи — его конец. Пишем только при изменениях,
# чтобы не трогать диск на каждый клик.

def _snapshot() -> str:
    parts = [name + df.to_json() for name, df in sorted(tables.items())]
    return json.dumps([parts, settings, st.session_state.wishes],
                      ensure_ascii=False, sort_keys=True, default=str)


try:
    fresh = _snapshot()
    if fresh != st.session_state.get("saved_snapshot"):
        save_tables(tables, settings, st.session_state.wishes)
        st.session_state.saved_snapshot = fresh
except Exception as error:  # noqa: BLE001 — потеря автосохранения не должна ронять экран
    st.toast(f"Не удалось сохранить данные: {error}", icon=":material/error:")
