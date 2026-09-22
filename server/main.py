"""FastAPI-приложение ЛАД.

Запуск локально:  .venv/bin/uvicorn server.main:app --reload
Интерфейс (web/dist) отдаётся этим же сервером, если собран.
"""

from __future__ import annotations

import asyncio
import base64
import hmac
import json
import os
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import ROOT, db
from .entry import router as entry_router
from .jobs import JOBS, start_job
from .journal import router as journal_router
from .sheets import router as sheets_router
from .tarif import router as tarif_router
from .whatif import router as whatif_router

from lad import explain, substitute  # noqa: E402
from lad.excel import to_bytes as excel_bytes  # noqa: E402
from lad.model import Slot  # noqa: E402
from lad.solve import (AIMS, PREFERENCES, PRESETS, RULE_SOURCES, RULE_TITLES,  # noqa: E402
                       Rules, assign_rooms)
from lad.storage import lessons_from_dict, lessons_to_dict  # noqa: E402
from lad.tables import build_school, check_norms, check_plan, tables_from_dict  # noqa: E402
from lad.quality import measure  # noqa: E402
from lad.validate import check  # noqa: E402

EXAMPLE = ROOT / "data" / "school.json"
DAY_NAMES = {1: "Понедельник", 2: "Вторник", 3: "Среда", 4: "Четверг", 5: "Пятница",
             6: "Суббота"}

app = FastAPI(title="ЛАД", version="0.1")
app.include_router(entry_router)  # ввод данных — server/entry.py
app.include_router(whatif_router)  # «что если» — server/whatif.py
app.include_router(sheets_router)  # листы файлом: PDF и Excel — server/sheets.py
app.include_router(journal_router)  # журнал замен по датам — server/journal.py
app.include_router(tarif_router)  # импорт чужой таблицы нагрузки — server/tarif.py

# ОБЩИЙ ПАРОЛЬ НА ВСЁ ПРИЛОЖЕНИЕ, если задан LAD_PASSWORD.
#
# Вход по почте — первое, что режется по плану (docs/PLAN.md), а открытое
# в интернет приложение с данными школы без замка оставлять нельзя. Базовая
# HTTP-авторизация браузера — самый короткий честный замок: окно ввода рисует
# сам браузер, пароль он запоминает и сам подставляет в fetch и EventSource.
# Имя пользователя любое, проверяется только пароль. Локально переменная
# не задана — замка нет. /api/health открыт: по нему хостинг проверяет, жив ли сервер.
PASSWORD = os.environ.get("LAD_PASSWORD", "")


@app.middleware("http")
async def password_gate(request: Request, call_next):
    if not PASSWORD or request.url.path == "/api/health":
        return await call_next(request)
    header = request.headers.get("authorization", "")
    if header.lower().startswith("basic "):
        try:
            _, _, given = base64.b64decode(header[6:]).decode("utf-8").partition(":")
        except (ValueError, UnicodeDecodeError):
            given = ""
        if hmac.compare_digest(given.encode(), PASSWORD.encode()):
            return await call_next(request)
    return Response("Нужен пароль ЛАД", status_code=401, media_type="text/plain; charset=utf-8",
                    headers={"WWW-Authenticate": 'Basic realm="LAD", charset="UTF-8"'})


# ---------------------------------------------------------------- помощники

def _load(school_id: str) -> tuple[dict, int]:
    found = db.get_school(school_id)
    if not found:
        raise HTTPException(404, "Школа не найдена")
    return found


def _build(doc: dict):
    return build_school(tables_from_dict(doc), doc.get("settings") or {}, doc.get("wishes"),
                        doc.get("targeted"))


def _report_dict(report) -> dict:
    data = asdict(report)
    data["summary"] = report.summary()
    data["norm_violations"] = len(report.norm_violations)
    data["structural_violations"] = len(report.structural_violations)
    return data


def _report(school, lessons) -> dict:
    """Отчёт валидатора плюс логика расписания сверх норм (lad/quality.py)."""
    data = _report_dict(check(school, lessons))
    data["logic"] = {k: v for k, v in measure(school, lessons).items() if k != "examples"}
    return data


def _directory(school) -> dict:
    """Справочник для отрисовки сетки: id → человеческие имена."""
    days = [d for d, kind in sorted(school.day_kinds.items()) if kind.value == "lessons"]
    return {
        "name": school.name,
        "days": [{"n": d, "name": DAY_NAMES[d]} for d in days],
        "periods": school.periods_per_day,
        "classes": [{"id": c.id, "name": c.name, "parallel": c.parallel} for c in school.classes],
        "groups": {g.id: {"class_ids": g.class_ids, "part": g.part} for g in school.groups},
        "teachers": {t.id: t.name for t in school.teachers},
        "subjects": {s.id: s.name for s in school.subjects},
        "rooms": {r.id: r.kind.value for r in school.rooms},
        # Карта трудности на экране расписания считается в браузере — после
        # каждого хода, без запроса: балл предмета для класса и рекомендованные
        # дни пика нагрузки (п. 94 ССЭТ).
        "difficulty": {c.id: {s.id: school.norms.difficulty(s.name, c.parallel) or 0 for s in school.subjects}
                       for c in school.classes},
        "peak_days": {c.id: school.norms.peak_days(c.parallel or 5) for c in school.classes},
    }


# ---------------------------------------------------------------- школы

@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


@app.get("/api/schools")
def schools() -> list[dict]:
    return db.list_schools()


class NewSchool(BaseModel):
    name: str = ""
    from_example: bool = False


@app.post("/api/schools")
def create_school(body: NewSchool) -> dict:
    if body.from_example:
        doc = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        # Пример открывает любой, у кого есть ссылка, — это показ третьим лицам
        # (CLAUDE.md §8.4). Нагрузка настоящая, ФИО учителей в файле уже
        # вымышленные (demo_city._names), а название школы — настоящее: убираем.
        doc.setdefault("settings", {})["name"] = "Средняя школа на 24 класса (пример)"
    else:
        doc = {"tables": {}, "settings": {"periods": 8, "days": 5, "sixth_day": True},
               "wishes": {}}
    if body.name:
        doc.setdefault("settings", {})["name"] = body.name
    return {"id": db.create_school(doc)}


@app.get("/api/schools/{school_id}")
def get_school(school_id: str) -> dict:
    doc, revision = _load(school_id)
    return {"id": school_id, "revision": revision, "doc": doc}


@app.put("/api/schools/{school_id}")
def put_school(school_id: str, doc: dict) -> dict:
    _load(school_id)
    return {"revision": db.save_school(school_id, doc)}


@app.get("/api/schools/{school_id}/revisions")
def revisions(school_id: str) -> list[dict]:
    return db.list_revisions(school_id)


@app.delete("/api/schools/{school_id}")
def delete_school(school_id: str) -> dict:
    """Удалить школу со всеми данными. Необратимо — интерфейс спрашивает дважды."""
    if not db.delete_school(school_id):
        raise HTTPException(404, "Школа не найдена")
    return {"ok": True}


@app.get("/api/schools/{school_id}/check")
def check_input(school_id: str) -> dict:
    """Проверки до запуска: ошибки ввода и предупреждения по нормам."""
    doc, _ = _load(school_id)
    school, problems = _build(doc)
    # Спортзалы — самое тесное место школы (замер 14.09.2026: 72 урока физкультуры
    # на 72 места в пн/ср/пт). Отдаём сырые цифры, а загрузку считает экран:
    # она зависит от того, разрешена ли физкультура два дня подряд.
    subject_names = {s.id: s.name for s in school.subjects}
    gyms = [r for r in school.rooms if r.kind.value == "gym"]
    pe = {
        "hours": sum(i.hours_per_week for i in school.load
                     if school.norms.is_pe(subject_names.get(i.subject_id, ""))),
        "gyms": len(gyms),
        "seats": sum(max(1, r.parallel_classes) for r in gyms),
        "periods": school.periods_per_day,
        "days": sum(1 for kind in school.day_kinds.values() if kind.value == "lessons"),
    }
    return {
        "problems": problems,
        "warnings": [] if problems else check_norms(school),
        # Сверка с типовым учебным планом № 75. Отдельно от норм: это не
        # нарушение, а вопрос к данным — школа вправе отступать от плана,
        # но чаще расхождение означает опечатку в тарификации.
        "plan": [] if problems else check_plan(school),
        # Что система домыслила за школу при импорте: кабинет наугад, учеников
        # по умолчанию, деление по двум учителям. Висит, пока не подтвердят.
        "assumptions": doc.get("assumptions") or [],
        "targeted": doc.get("targeted") or [],
        "stats": {"classes": len(school.classes), "teachers": len(school.teachers),
                  "rooms": len(school.rooms),
                  "hours": sum(item.hours_per_week for item in school.load)},
        "pe": pe,
    }


# ---------------------------------------------------------------- составление

class TargetedBody(BaseModel):
    rows: list[dict]


@app.put("/api/schools/{school_id}/targeted")
def save_targeted(school_id: str, body: TargetedBody) -> dict:
    """Адресные пожелания школы: «кому → что → насколько»."""
    doc, _ = _load(school_id)
    doc["targeted"] = body.rows
    return {"revision": db.save_school(school_id, doc)}


@app.delete("/api/schools/{school_id}/assumptions")
def clear_assumptions(school_id: str) -> dict:
    """«Проверил» — убрать список предположений из данных школы."""
    doc, _ = _load(school_id)
    doc.pop("assumptions", None)
    return {"revision": db.save_school(school_id, doc)}


@app.get("/api/rules")
def rules() -> dict:
    defaults = Rules()
    return {
        "rules": [{"key": key, "title": title, "source": RULE_SOURCES.get(key),
                   "default": getattr(defaults, key)} for key, title in RULE_TITLES.items()],
        "presets": [{"name": name, "about": value["about"]} for name, value in PRESETS.items()],
        "preferences": [{k: p[k] for k in ("key", "group", "title", "about", "default")} for p in PREFERENCES],
        # Адресные пожелания-числа: «не больше шести уроков в день»,
        # «информатика не в понедельник». У них не «насколько важно», а величина.
        "aims": AIMS,
    }


class SolveRequest(BaseModel):
    budget: float = 300
    preset: str = "Поровну"
    rules: dict[str, str] = {}
    prefs: dict[str, int] = {}  # предпочтения школы: уровень 0–3 и light_day_of_week
    pinned: list[dict] | None = None
    hint: list[dict] | None = None  # текущая сетка — старт пересборки вокруг закреплённых
    keep: bool = False  # беречь текущую сетку: штраф за каждый урок, ушедший со своего места
    settle: float | None = None  # остановиться раньше, если нормы на нуле и улучшений нет столько секунд


@app.post("/api/schools/{school_id}/solve")
def solve(school_id: str, body: SolveRequest) -> dict:
    doc, revision = _load(school_id)

    def on_result(job) -> None:
        result = job.result or {}
        if result.get("type") == "result" and result.get("lessons"):
            job.schedule_id = db.save_schedule(
                school_id, revision, result["lessons"],
                {**{key: result.get(key) for key in ("status", "seconds", "penalty", "relaxed")},
                 # Откуда версия — для списка версий: составление с нуля или пересборка.
                 "kind": "rebuild" if body.keep else "solve", "pinned": len(body.pinned or [])})

    job = start_job(school_id, revision, doc, body.model_dump(), on_result)
    return {"job_id": job.id}


@app.post("/api/jobs/{job_id}/stop")
def stop(job_id: str) -> dict:
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "Задача не найдена")
    job.stop()
    return {"ok": True}


@app.get("/api/jobs/{job_id}/events")
async def events(job_id: str) -> StreamingResponse:
    """Ход составления потоком событий: снимки прогресса, затем итог."""
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "Задача не найдена")

    async def stream():
        sent = 0
        setup_sent = False
        while True:
            if job.setup and not setup_sent:
                yield f"event: setup\ndata: {json.dumps(job.setup, ensure_ascii=False)}\n\n"
                setup_sent = True
            while sent < len(job.history):
                yield f"event: progress\ndata: {json.dumps(job.history[sent], ensure_ascii=False)}\n\n"
                sent += 1
            if job.finished:
                result = dict(job.result or {})
                result.pop("lessons", None)
                result["schedule_id"] = job.schedule_id
                yield f"event: done\ndata: {json.dumps(result, ensure_ascii=False)}\n\n"
                return
            await asyncio.sleep(0.5)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache"})


# ---------------------------------------------------------------- расписания

def _schedule_payload(school_id: str, row: dict | None) -> dict:
    if row is None:
        raise HTTPException(404, "Расписания ещё нет")
    doc, _ = _load(school_id)
    school, problems = _build(doc)
    lessons = lessons_from_dict(row["lessons"])
    return {
        "id": row["id"], "meta": row["meta"], "created_at": row["created_at"],
        "stale": row["revision_id"] != db.get_school(school_id)[1],
        "directory": _directory(school),
        "lessons": row["lessons"],
        "report": _report(school, lessons) if not problems else None,
    }


@app.get("/api/schools/{school_id}/schedules/latest")
def latest(school_id: str) -> dict:
    return _schedule_payload(school_id, db.latest_schedule(school_id))


@app.get("/api/schools/{school_id}/schedules/{schedule_id}")
def schedule(school_id: str, schedule_id: str) -> dict:
    return _schedule_payload(school_id, db.get_schedule(schedule_id))


class LessonsBody(BaseModel):
    lessons: list[dict]


@app.post("/api/schools/{school_id}/validate")
def validate(school_id: str, body: LessonsBody) -> dict:
    """Проверить произвольную сетку — после ручной правки."""
    doc, _ = _load(school_id)
    school, problems = _build(doc)
    if problems:
        raise HTTPException(422, {"problems": problems})
    return _report(school, lessons_from_dict(body.lessons))


def _verdict_dict(verdict) -> dict:
    return asdict(verdict)


class MoveBody(BaseModel):
    lessons: list[dict]
    index: int
    day: int | None = None
    period: int | None = None


@app.post("/api/schools/{school_id}/heatmap")
def heatmap(school_id: str, body: MoveBody) -> dict:
    """Подсветка недели для перетаскиваемого урока: «день-урок» → оценка."""
    doc, _ = _load(school_id)
    school, problems = _build(doc)
    if problems:
        raise HTTPException(422, {"problems": problems})
    lessons = lessons_from_dict(body.lessons)
    if not 0 <= body.index < len(lessons):
        raise HTTPException(422, "Нет такого урока")
    return {key: _verdict_dict(v) for key, v in explain.heatmap(school, lessons, body.index).items()}


@app.post("/api/schools/{school_id}/move")
def move(school_id: str, body: MoveBody) -> dict:
    """Оценить один ход и вернуть сетку после него — применять или нет, решает завуч."""
    doc, _ = _load(school_id)
    school, problems = _build(doc)
    if problems:
        raise HTTPException(422, {"problems": problems})
    lessons = lessons_from_dict(body.lessons)
    if not 0 <= body.index < len(lessons) or body.day is None or body.period is None:
        raise HTTPException(422, "Нужны урок и клетка")
    source = lessons[body.index].slot
    target = Slot(body.day, body.period, source.shift)
    verdict = explain.evaluate_move(school, lessons, body.index, target)
    lessons = explain.apply_move(lessons, verdict, source, target)
    assign_rooms(school, lessons)
    return {"verdict": _verdict_dict(verdict), "lessons": lessons_to_dict(lessons),
            "report": _report(school, lessons)}


class SaveBody(BaseModel):
    lessons: list[dict]
    name: str | None = None  # «после замены Ивановой» — чтобы версию узнали в списке


@app.post("/api/schools/{school_id}/schedules")
def save_edited(school_id: str, body: SaveBody) -> dict:
    """Сохранить сетку после ручной правки как новую версию."""
    _, revision = _load(school_id)
    meta = {"status": "EDITED", **({"name": body.name.strip()} if body.name and body.name.strip() else {})}
    return {"id": db.save_schedule(school_id, revision, body.lessons, meta)}


def _version_title(meta: dict) -> str:
    if meta.get("accepted"):
        return f"Принято из «Что если»: {meta['accepted']}"
    if meta.get("status") == "EDITED":
        return "Ручная правка"
    if meta.get("status") == "RESTORED":
        return "Возврат к прежней версии"
    if meta.get("kind") == "rebuild":
        return "Пересборка вокруг закреплённых"
    return "Составлено автоматически"


@app.get("/api/schools/{school_id}/schedules")
def versions(school_id: str) -> list[dict]:
    """Версии расписания: каждое составление, пересборка и сохранение правки.

    Цифры версии (нарушения, окна) считаются один раз и кладутся в её meta —
    по данным школы ТОЙ ревизии, по которой версия составлена: иначе старая
    версия после правки нагрузки показывала бы конфликты, которых в ней не было.
    """
    _, revision = _load(school_id)
    built: dict[int, object] = {}
    result = []
    for n, row in enumerate(db.list_schedules(school_id)):
        meta = row["meta"]
        summary = meta.get("summary")
        if summary is None and row["revision_id"] is not None:
            if row["revision_id"] not in built:
                doc = db.get_revision(row["revision_id"])
                school, problems = _build(doc) if doc else (None, ["нет ревизии"])
                built[row["revision_id"]] = None if problems else school
            school = built[row["revision_id"]]
            if school is not None:
                full = db.get_schedule(row["id"])
                report = check(school, lessons_from_dict(full["lessons"]))
                summary = {"norms": len(report.norm_violations), "gaps": report.teacher_gaps,
                           "conflicts": len(report.structural_violations)}
                db.update_schedule_meta(row["id"], {**meta, "summary": summary})
        result.append({"id": row["id"], "created_at": row["created_at"], "title": _version_title(meta),
                       "name": meta.get("name"), "summary": summary, "current": n == 0,
                       "stale": row["revision_id"] != revision})
    return result


@app.post("/api/schools/{school_id}/schedules/{schedule_id}/restore")
def restore(school_id: str, schedule_id: str) -> dict:
    """Сделать прежнюю версию текущей: копия встаёт последней, история не теряется."""
    _load(school_id)
    row = db.get_schedule(schedule_id)
    if not row or row["school_id"] != school_id or row["meta"].get("change"):
        raise HTTPException(404, "Версия не найдена")
    meta = {k: v for k, v in row["meta"].items() if k in ("seconds", "relaxed", "name", "summary")}
    new_id = db.save_schedule(school_id, row["revision_id"], row["lessons"],
                              {**meta, "status": "RESTORED", "from": schedule_id, "from_at": row["created_at"]})
    return {"schedule_id": new_id}


@app.post("/api/schools/{school_id}/export.xlsx")
def export_xlsx(school_id: str, body: LessonsBody, anonymize: bool = False) -> Response:
    doc, _ = _load(school_id)
    school, _ = _build(doc)
    data = excel_bytes(school, lessons_from_dict(body.lessons), anonymize=anonymize)
    return Response(data, media_type="application/vnd.openxmlformats-officedocument."
                                     "spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="raspisanie.xlsx"'})


# ---------------------------------------------------------------- замены

class SubstituteBody(BaseModel):
    teacher_id: str
    day: int  # день недели: 1 = понедельник
    lessons: list[dict] | None = None  # сетка; по умолчанию — последняя сохранённая


@app.post("/api/schools/{school_id}/substitutions")
def substitutions(school_id: str, body: SubstituteBody) -> dict:
    """Кто проведёт уроки отсутствующего учителя — кандидаты с причинами."""
    doc, _ = _load(school_id)
    school, problems = _build(doc)
    if problems:
        raise HTTPException(422, {"problems": problems})
    if body.lessons is None:
        row = db.latest_schedule(school_id)
        if row is None:
            raise HTTPException(404, "Расписания ещё нет")
        body.lessons = row["lessons"]
    teacher = next((t for t in school.teachers if t.id == body.teacher_id), None)
    if teacher is None:
        raise HTTPException(404, "Учитель не найден")
    needs = substitute.plan(school, lessons_from_dict(body.lessons), body.teacher_id, body.day)
    return {"teacher": teacher.name, "day": body.day, "day_name": DAY_NAMES.get(body.day, ""),
            "needs": [asdict(n) for n in needs]}


# ---------------------------------------------------------------- интерфейс

WEB_DIST = ROOT / "web" / "dist"
if WEB_DIST.exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str) -> FileResponse:
        file = WEB_DIST / path
        return FileResponse(file if path and file.is_file() else WEB_DIST / "index.html")
