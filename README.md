---
title: ЛАД — расписание школы
emoji: 🏫
colorFrom: gray
colorTo: blue
sdk: streamlit
sdk_version: 1.62.0
app_file: app.py
python_version: "3.13"
pinned: false
short_description: Автосоставление школьного расписания по санитарным нормам РБ
---

# ЛАД

**Л**огистика **А**кадемического **Д**ня — MVP автосоставления школьного расписания
на OR-Tools CP-SAT.

Контекст проекта — `CLAUDE.md`. Рабочий лог — `STATUS.md`.

## Запуск

```
.venv/bin/streamlit run app.py
```

Данные школы лежат в `data/school.json`, результат — в `out/`.

## Развёртывание

Блок в начале файла — конфигурация Hugging Face Spaces: заголовок, движок
(`streamlit`) и версия Python. Версия важна: `ortools` собирает колёса
до 3.13 включительно, на 3.14 установка упадёт. На GitHub этот блок
не мешает — он просто не отображается в отрендеренном README.

Streamlit Community Cloud тот же блок игнорирует и берёт версию Python
из `.python-version`, поэтому оба развёртывания живут с одного репозитория.
