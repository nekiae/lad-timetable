"""Рендер расписания в один самодостаточный HTML-файл.

Файл открывается двойным кликом, пересылается в мессенджер, читается с телефона.
Ни одного внешнего запроса: стили, скрипт и данные внутри.

Рендер ничего не знает про солвер — он принимает уроки и школу, неважно откуда
(CLAUDE.md §7.1). Поэтому реальное расписание школы рисуется этим же кодом.
"""

import json
from collections import defaultdict

from .model import Lesson, School
from .validate import Report, check

DAYS = ["", "Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота"]
SHORT_DAYS = ["", "Пн", "Вт", "Ср", "Чт", "Пт", "Сб"]

# Сводная сетка «все классы × вся неделя» — это лист, который висит в учительской.
# В колонку шириной с ноготь полное название предмета не входит, поэтому нужны
# те же сокращения, которыми пишут от руки.
SHORT_SUBJECTS = {
    "белорусский язык": "Бел. яз.",
    "белорусская литература": "Бел. лит.",
    "русский язык": "Рус. яз.",
    "русская литература": "Рус. лит.",
    "иностранный язык": "Ин. яз.",
    "математика": "Матем.",
    "информатика": "Инф.",
    "человек и мир": "Чел. и мир",
    "всемирная история": "Всем. ист.",
    "история беларуси": "Ист. Бел.",
    "история беларуси в контексте всемирной истории": "Ист. Бел.",
    "обществоведение": "Обществ.",
    "география": "Геогр.",
    "биология": "Биол.",
    "астрономия": "Астрон.",
    "черчение": "Черч.",
    "трудовое обучение": "Труд",
    "физическая культура и здоровье": "Физ-ра",
    "основы безопасности жизнедеятельности": "ОБЖ",
    "допризывная и медицинская подготовка": "ДМП",
    "искусство (отечественная и мировая художественная культура)": "Искусство",
}


def _short(name: str) -> str:
    """Короткая подпись предмета: из словаря, иначе первое слово с точкой."""
    key = name.strip().lower()
    if key in SHORT_SUBJECTS:
        return SHORT_SUBJECTS[key]
    if len(name) <= 11:
        return name
    first = name.split()[0]
    return first if len(first) <= 11 else first[:9] + "."


def _anonymize_name(index: int) -> str:
    return f"Учитель {index}"


def _grid(school: School, lessons: list[Lesson], teacher_names: dict[str, str]) -> dict:
    """Данные для отрисовки: класс → день → урок → список занятий."""
    subjects = {s.id: s.name for s in school.subjects}
    grid: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for lesson in lessons:
        group = school.group(lesson.group_id)
        label = subjects.get(lesson.subject_id, lesson.subject_id)
        if group.part is not None:
            label += f" ({group.part} гр.)"
        short = _short(subjects.get(lesson.subject_id, lesson.subject_id))
        if group.part is not None:
            short += f" ({group.part})"
        entry = {
            "subject": label,
            "short": short,
            "teacher": teacher_names.get(lesson.teacher_id, lesson.teacher_id),
            "room": lesson.room_id or "",
        }
        for class_id in group.class_ids:
            grid[class_id][lesson.slot.day][lesson.slot.period].append(entry)
    return grid


def render(
    school: School,
    lessons: list[Lesson],
    before: list[Lesson] | None = None,
    anonymize: bool = False,
    minutes_spent: float | None = None,
) -> str:
    """Собрать HTML. `before` — реальное расписание школы, если оно введено."""
    teacher_names = {t.id: t.name for t in school.teachers}
    if anonymize:
        teacher_names = {t.id: _anonymize_name(i + 1) for i, t in enumerate(school.teachers)}

    after_report = check(school, lessons)
    before_report = check(school, before) if before else None

    days = [d for d, kind in sorted(school.day_kinds.items()) if kind.value == "lessons"]
    payload = {
        "classes": [c.name for c in school.classes],
        "classIds": [c.id for c in school.classes],
        "days": [DAYS[d] for d in days],
        "daysShort": [SHORT_DAYS[d] for d in days],
        "dayNums": days,
        "periods": school.periods_per_day,
        "after": _grid(school, lessons, teacher_names),
        "before": _grid(school, before, teacher_names) if before else None,
    }

    cards = _metric_cards(after_report, before_report, minutes_spent)
    school_name = "Школа" if anonymize else school.name

    return _TEMPLATE.format(
        title=f"Расписание — {school_name}",
        school=school_name,
        cards=cards,
        toggle="" if before is None else _TOGGLE,
        data=json.dumps(payload, ensure_ascii=False),
        violations=_violations_block(after_report, before_report),
    )


def _metric_cards(after: Report, before: Report | None, minutes: float | None) -> str:
    rows = []
    for label, value in after.summary().items():
        if before is None:
            rows.append(
                f'<div class="card"><div class="num">{value}</div>'
                f'<div class="lbl">{label}</div></div>'
            )
        else:
            was = before.summary()[label]
            better = value < was
            same = value == was
            arrow = "→"
            cls = "good" if better else ("same" if same else "bad")
            rows.append(
                f'<div class="card {cls}"><div class="num">'
                f'<span class="was">{was}</span> {arrow} <span>{value}</span></div>'
                f'<div class="lbl">{label}</div></div>'
            )
    if minutes is not None:
        spent = (f"{minutes * 60:.0f} с" if minutes < 1
                 else (f"{minutes:.0f} мин" if minutes < 60 else f"{minutes / 60:.1f} ч"))
        rows.append(
            f'<div class="card good"><div class="num">'
            f'<span class="was">~2 недели</span> → <span>{spent}</span></div>'
            f'<div class="lbl">Время составления</div></div>'
        )
    return "\n".join(rows)


def _violations_block(after: Report, before: Report | None) -> str:
    if not after.violations and not (before and before.violations):
        return '<p class="ok">Жёсткие правила не нарушены.</p>'
    parts = []
    if before and before.violations:
        parts.append(
            f'<details><summary>Нарушений в текущем расписании школы: '
            f'{len(before.violations)}</summary><ul>'
            + "".join(f"<li><b>{v.rule}</b> — {v.what} <i>({v.where})</i></li>"
                      for v in before.violations[:100])
            + "</ul></details>"
        )
    if after.violations:
        parts.append(
            f'<details open><summary>Нарушений в составленном расписании: '
            f'{len(after.violations)}</summary><ul>'
            + "".join(f"<li><b>{v.rule}</b> — {v.what} <i>({v.where})</i></li>"
                      for v in after.violations[:100])
            + "</ul></details>"
        )
    return "\n".join(parts)


_TOGGLE = """
    <div class="toggle">
      <button id="btn-after" class="active" onclick="setMode('after')">Составленное</button>
      <button id="btn-before" onclick="setMode('before')">Текущее расписание школы</button>
    </div>
"""

_TEMPLATE = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  :root {{
    --bg: #fbfbfa; --fg: #1c1b1a; --muted: #6b6a68; --line: #e3e1dd;
    --card: #ffffff; --good: #2f7d4f; --bad: #b4402f; --accent: #2b5f8f;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg: #17161a; --fg: #eceae6; --muted: #9a9894; --line: #2f2d33;
      --card: #201f24; --good: #6fbf8b; --bad: #e08471; --accent: #7aa8d6;
    }}
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; padding: 24px; background: var(--bg); color: var(--fg);
    font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif; }}
  .wrap {{ max-width: 1100px; margin: 0 auto; }}
  h1 {{ font-size: 22px; margin: 0 0 4px; }}
  .sub {{ color: var(--muted); margin-bottom: 24px; font-size: 14px; }}
  .cards {{ display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(215px, 1fr));
    margin-bottom: 24px; }}
  .card {{ background: var(--card); border: 1px solid var(--line); border-radius: 10px;
    padding: 14px 16px; }}
  .card .num {{ font-size: 21px; font-weight: 600; letter-spacing: -0.02em;
    line-height: 1.25; }}
  .card .lbl {{ color: var(--muted); font-size: 13px; margin-top: 4px; }}
  .card .was {{ color: var(--muted); font-weight: 400; }}
  .card.good .num > span:last-child {{ color: var(--good); }}
  .card.bad .num > span:last-child {{ color: var(--bad); }}
  .toggle {{ display: inline-flex; border: 1px solid var(--line); border-radius: 8px;
    overflow: hidden; margin-bottom: 16px; }}
  .toggle button {{ border: 0; background: var(--card); color: var(--fg); padding: 8px 14px;
    font: inherit; cursor: pointer; }}
  .toggle button.active {{ background: var(--accent); color: #fff; }}
  select {{ font: inherit; padding: 7px 10px; border-radius: 8px; border: 1px solid var(--line);
    background: var(--card); color: var(--fg); margin-bottom: 16px; }}
  .views {{ display: inline-flex; border: 1px solid var(--line); border-radius: 8px;
    overflow: hidden; margin: 0 12px 16px 0; }}
  .views button {{ border: 0; background: var(--card); color: var(--fg); padding: 8px 14px;
    font: inherit; cursor: pointer; }}
  .views button.active {{ background: var(--accent); color: #fff; }}
  .controls {{ display: flex; gap: 10px; flex-wrap: wrap; }}
  .scroll {{ overflow-x: auto; }}

  /* Сводная сетка: 28 классов в ширину и 40 строк в высоту читаются, только
     если шапка и первый столбец не уезжают. Отсюда sticky. */
  table.all {{ min-width: 0; font-size: 12.5px; }}
  table.all th, table.all td {{ padding: 4px 6px; white-space: nowrap; }}
  table.all thead th {{ position: sticky; top: 0; z-index: 3; background: var(--card); }}
  table.all td.day, table.all th.day {{ position: sticky; left: 0; z-index: 2;
    background: var(--card); font-weight: 600; }}
  table.all td.per {{ position: sticky; left: 42px; z-index: 2; background: var(--card);
    color: var(--muted); text-align: center; }}
  table.all thead th:first-child {{ left: 0; z-index: 4; }}
  table.all tr.daystart td {{ border-top: 2px solid var(--fg); }}
  table.all td .rm {{ color: var(--muted); font-size: 11px; margin-left: 3px; }}
  table {{ border-collapse: collapse; width: 100%; min-width: 720px; }}
  th, td {{ border: 1px solid var(--line); padding: 8px 10px; text-align: left;
    vertical-align: top; }}
  th {{ background: var(--card); font-weight: 600; font-size: 13px; }}
  td.num {{ color: var(--muted); width: 34px; text-align: center; }}
  .cell b {{ display: block; font-weight: 500; }}
  .cell i {{ color: var(--muted); font-style: normal; font-size: 12.5px; }}
  .empty {{ color: var(--line); }}
  details {{ margin-top: 20px; }}
  summary {{ cursor: pointer; color: var(--muted); }}
  li {{ margin: 3px 0; }}
  .ok {{ color: var(--good); }}
  footer {{ margin-top: 32px; color: var(--muted); font-size: 12.5px;
    border-top: 1px solid var(--line); padding-top: 12px; }}
</style></head><body><div class="wrap">
  <h1>{school}</h1>
  <div class="sub">Расписание составлено системой ЛАД — Логистика Академического Дня</div>
  <div class="cards">{cards}</div>
  {toggle}
  <div class="views">
    <button id="v-one" class="active" onclick="setView('one')">Один класс</button>
    <button id="v-all" onclick="setView('all')">Вся школа</button>
  </div>
  <div class="controls">
    <select id="cls" onchange="draw()"></select>
    <select id="day" onchange="draw()" hidden></select>
  </div>
  <div class="scroll"><table id="grid"></table></div>
  {violations}
  <footer>
    Метрики «было» и «стало» считает один и тот же валидатор.<br>
    Санитарные нормы применяются только если введены из первоисточника.
  </footer>
</div>
<script>
const D = {data};
let mode = 'after';

const sel = document.getElementById('cls');
D.classes.forEach((name, i) => {{
  const o = document.createElement('option');
  o.value = D.classIds[i]; o.textContent = name; sel.appendChild(o);
}});

function setMode(m) {{
  mode = m;
  document.getElementById('btn-after').classList.toggle('active', m === 'after');
  document.getElementById('btn-before').classList.toggle('active', m === 'before');
  draw();
}}

const daySel = document.getElementById('day');
const optAll = document.createElement('option');
optAll.value = 'all'; optAll.textContent = 'Все дни'; daySel.appendChild(optAll);
D.dayNums.forEach((num, i) => {{
  const o = document.createElement('option');
  o.value = num; o.textContent = D.days[i]; daySel.appendChild(o);
}});

let view = 'one';

function setView(v) {{
  view = v;
  document.getElementById('v-one').classList.toggle('active', v === 'one');
  document.getElementById('v-all').classList.toggle('active', v === 'all');
  sel.hidden = v !== 'one';
  daySel.hidden = v !== 'all';
  draw();
}}

function esc(s) {{ return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;'); }}

/* Один класс: день × урок — то, что видит класс у себя в кабинете. */
function drawOne(data) {{
  let html = '<tr><th></th>' + D.days.map(d => '<th>' + d + '</th>').join('') + '</tr>';
  for (let p = 1; p <= D.periods; p++) {{
    html += '<tr><td class="num">' + p + '</td>';
    for (const day of D.dayNums) {{
      const items = ((data[day] || {{}})[p]) || [];
      html += '<td>' + (items.length
        ? items.map(x => '<div class="cell"><b>' + esc(x.subject) + '</b><i>' +
            esc(x.teacher) + (x.room ? ' · ' + esc(x.room) : '') + '</i></div>').join('')
        : '<span class="empty">—</span>') + '</td>';
    }}
    html += '</tr>';
  }}
  return html;
}}

/* Вся школа: строки — день и урок, столбцы — классы. Тот самый лист,
   который висит в учительской: сразу видно, кто где в конкретный час. */
/* До какого урока вообще занят день: восемь строк, из которых три пустые,
   удлиняют лист на треть и ничего не сообщают. */
function lastPeriod(all, day) {{
  let last = 1;
  for (const cid of D.classIds) {{
    const byPeriod = ((all[cid] || {{}})[day] || {{}});
    for (let p = D.periods; p > last; p--) {{
      if ((byPeriod[p] || []).length) {{ last = p; break; }}
    }}
  }}
  return last;
}}

function drawAll(all) {{
  const days = daySel.value === 'all'
    ? D.dayNums : [parseInt(daySel.value, 10)];
  let html = '<thead><tr><th class="day">День</th><th></th>' +
    D.classes.map(c => '<th>' + esc(c) + '</th>').join('') + '</tr></thead><tbody>';
  days.forEach(day => {{
    const label = D.daysShort[D.dayNums.indexOf(day)];
    const last = lastPeriod(all, day);
    for (let p = 1; p <= last; p++) {{
      const first = p === 1;
      html += '<tr' + (first ? ' class="daystart"' : '') + '>';
      html += first
        ? '<td class="day" rowspan="' + last + '">' + label + '</td>'
        : '';
      html += '<td class="per">' + p + '</td>';
      for (const cid of D.classIds) {{
        const items = (((all[cid] || {{}})[day] || {{}})[p]) || [];
        html += '<td>' + (items.length
          ? items.map(x => '<span title="' + esc(x.subject + ' · ' + x.teacher) + '">' +
              esc(x.short) + (x.room ? '<span class="rm">' + esc(x.room) + '</span>' : '') +
              '</span>').join('<br>')
          : '<span class="empty">·</span>') + '</td>';
      }}
      html += '</tr>';
    }}
  }});
  return html + '</tbody>';
}}

function draw() {{
  const all = D[mode] || {{}};
  const grid = document.getElementById('grid');
  grid.className = view === 'all' ? 'all' : '';
  grid.innerHTML = view === 'all' ? drawAll(all) : drawOne(all[sel.value] || {{}});
}}
draw();
</script></body></html>
"""
