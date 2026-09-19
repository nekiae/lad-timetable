"""Срез сетки для лендинга.

Берёт готовое расписание из out/schedule.json и вырезает несколько классов.
Подгруппы (иностранный язык, трудовое) идут отдельными группами и в одном
слоте с классом — их обязательно надо включать, иначе в сетке появляются
дыры, то есть окна у класса, которых система не допускает (HARD-8).

    python3 landing/tools/build-grid.py
"""

import collections
import json
import pathlib

CORNI = pathlib.Path(__file__).resolve().parents[2]
VHOD = CORNI / "out" / "schedule.json"
VYHOD = CORNI / "landing" / "src" / "data" / "grid.json"

KLASSY = ["5А", "6Б", "7А", "8В", "9Б", "11А"]
DNEY = 5
UROKOV = 7

KOROTKO = {
    "Белорусский язык": "Бел. яз.",
    "Белорусская литература": "Бел. лит.",
    "Русский язык": "Рус. яз.",
    "Русская литература": "Рус. лит.",
    "Иностранный язык": "Ин. яз.",
    "Английский язык": "Англ. яз.",
    "История Беларуси": "История Бел.",
    "Всемирная история": "Всем. история",
    "Обществоведение": "Обществовед.",
    "Физическая культура и здоровье": "Физкультура",
    "Трудовое обучение": "Труд",
    "Искусство (отечественная и мировая художественная культура)": "Искусство",
    "Допризывная подготовка": "Допризывная",
    "Основы безопасности жизнедеятельности": "ОБЖ",
    "История Беларуси в контексте всемирной истории": "История Бел.",
    "Человек и мир": "Человек и мир",
}


def main() -> None:
    dannye = json.loads(VHOD.read_text())
    shkola = dannye["school"]
    predmety = {x["id"]: x["name"] for x in shkola["subjects"]}
    uchitelya = {x["id"]: x["name"] for x in shkola["teachers"]}
    # Группа → класс, которому она принадлежит. Для подгрупп это родительский
    # класс, для обычной группы — она сама.
    klass_gruppy = {
        g["id"]: g["class_ids"][0] for g in shkola["groups"] if g["class_ids"]
    }

    kletki: dict[str, dict[str, dict]] = collections.defaultdict(dict)
    for urok in dannye["lessons"]:
        klass = klass_gruppy.get(urok["group_id"])
        if klass not in KLASSY:
            continue
        if urok["day"] > DNEY or urok["period"] > UROKOV:
            continue
        kluch = f"{urok['day']}-{urok['period']}"
        predmet = predmety.get(urok["subject_id"], "?")
        uchitel = uchitelya.get(urok["teacher_id"], "?")
        est = kletki[klass].get(kluch)
        if est is None:
            kletki[klass][kluch] = {
                "s": KOROTKO.get(predmet, predmet),
                "t": uchitel,
                "r": urok["room_id"],
            }
        else:
            # Две подгруппы в одном слоте: показываем предмет один раз,
            # а вместо фамилии говорим, что класс поделён.
            est["t"] = "две подгруппы"
            est["r"] = "2 кабинета"

    dyry = []
    for klass in KLASSY:
        for d in range(1, DNEY + 1):
            uroki = [p for p in range(1, UROKOV + 1) if f"{d}-{p}" in kletki[klass]]
            if not uroki:
                continue
            for p in range(min(uroki), max(uroki) + 1):
                if f"{d}-{p}" not in kletki[klass]:
                    dyry.append(f"{klass} день {d} урок {p}")

    VYHOD.write_text(
        json.dumps(
            {
                "classes": KLASSY,
                "days": ["Пн", "Вт", "Ср", "Чт", "Пт"],
                "periods": UROKOV,
                "cells": {k: kletki[k] for k in KLASSY},
            },
            ensure_ascii=False,
            indent=1,
        )
    )
    vsego = sum(len(v) for v in kletki.values())
    print(f"классов {len(KLASSY)}, клеток {vsego}")
    print("окон у классов:", len(dyry) or "нет")
    for d in dyry[:20]:
        print("  ", d)


if __name__ == "__main__":
    main()
