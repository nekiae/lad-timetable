"""Независимая проверка расписания: считаем с нуля, не используя lad.validate."""
import sys, json, collections, re
sys.path.insert(0, "src")
import pandas as pd
from lad.tables import blank_tables, build_school
from lad.storage import load_schedule

which = sys.argv[1]
raw = json.load(open(f"data/{which}.json"))
tabs = {k: pd.DataFrame(v) for k, v in raw["tables"].items()}
for n, df in blank_tables().items():
    if n not in tabs: tabs[n] = df
school, _ = build_school(tabs, raw["settings"], {})

# восстанавливаем расписание из HTML-независимого источника: пересобираем из json отчёта нельзя,
# поэтому решаем заново нельзя — берём schedule из out/demo (сохраняли только html/xlsx).
# Вместо этого проверяем на свежем прогоне с тем же seed — здесь просто пересчитаем метрики
# по HTML: разбираем встроенный JSON.
import re
html = open(f"out/demo/{which}.html", encoding="utf-8").read()
m = re.search(r'const D = (\{.*?\});\n', html, re.S)
data = json.loads(m.group(1))
grid = data["after"]   # {classId: {day: {period: [ {subject, teacher, room}, ...]}}}

fails = collections.Counter()
teacher_slot = collections.defaultdict(list)
room_slot = collections.defaultdict(list)
class_slot = collections.defaultdict(list)
counts = collections.Counter()

for class_id, days in grid.items():
    for day, periods in days.items():
        for period, items in periods.items():
            for it in items:
                key = (day, period)
                teacher_slot[(it["teacher"], day, period)].append(class_id)
                if it.get("room"): room_slot[(it["room"], day, period)].append(class_id)
                class_slot[(class_id, day, period)].append(it["subject"])
                # в сетке подгруппа подписана «Предмет (1 гр.)» — для сверки
                # с нагрузкой суффикс надо убрать
                bare = re.sub(r"\s*\(\d+ гр\.\)$", "", it["subject"])
                counts[(class_id, bare, str(day), str(period))] += 1

for (t, d, p), where in teacher_slot.items():
    if len(where) > 1: fails["учитель в двух местах"] += 1
for (r, d, p), where in room_slot.items():
    if len(where) > 1: fails["кабинет занят дважды"] += 1
# окна у класса: уроки должны идти подряд с первого
for class_id, days in grid.items():
    for day, periods in days.items():
        nums = sorted(int(p) for p in periods)
        if nums and nums != list(range(1, len(nums) + 1)):
            fails["окно у класса"] += 1

# все ли часы выданы
need = collections.Counter()
subj = {s.id: s.name for s in school.subjects}
cls_name = {c.id: c.name for c in school.classes}
for item in school.load:
    for cid in school.group(item.group_id).class_ids:
        key = (cls_name[cid], subj[item.subject_id])
        need[key] = max(need[key], item.hours_per_week) if school.group(item.group_id).part \
            else need[key] + item.hours_per_week
# часы считаем по УНИКАЛЬНЫМ слотам: две подгруппы в одном слоте — это один час
slots_of = collections.defaultdict(set)
for (cid, subject, day, period) in counts:
    slots_of[(cid, subject)].add((day, period))
short = []
for key, want in need.items():
    got = len(slots_of.get(key, ()))
    if got != want:
        short.append(f"{key[0]} {key[1]}: нужно {want}, стоит {got}")
        fails["часы не сходятся"] += 1

print(f"{school.name}: независимая проверка")
print("  уроков в сетке:", sum(len(i) for d in grid.values() for p in d.values() for i in p.values()))
print("  нарушений:", dict(fails) if fails else "НЕТ")
for line in short[:5]: print("     ", line)
