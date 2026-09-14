"""FastAPI-приложение ЛАД.

Запуск локально:  .venv/bin/uvicorn server.main:app --reload
Интерфейс (web/dist) отдаётся этим же сервером, если собран.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import ROOT, db
from .jobs import JOBS, start_job

from lad.excel import to_bytes as excel_bytes  # noqa: E402
from lad.solve import PRESETS, RULE_SOURCES, RULE_TITLES, Rules  # noqa: E402
from lad.storage import lessons_from_dict  # noqa: E402
from lad.tables import build_school, check_norms, tables_from_dict  # noqa: E402
from lad.validate import check  # noqa: E402

EXAMPLE = ROOT / "data" / "school.json"
DAY_NAMES = {1: "Понедельник", 2: "Вторник", 3: "Среда", 4: "Четверг", 5: "Пятница",
             6: "Суббота"}

app = FastAPI(title="ЛАД", version="0.1")


# ---------------------------------------------------------------- помощники

def _load(school_id: str) -> tuple[dict, int]:
    found = db.get_school(school_id)
    if not found:
        raise HTTPException(404, "Школа не найдена")
    return found


def _build(doc: dict):
    return build_school(tables_from_dict(doc), doc.get("settings") or {}, doc.get("wishes"))


def _report_dict(report) -> dict:
    data = asdict(report)
    data["summary"] = report.summary()
    data["norm_violations"] = len(report.norm_violations)
    data["structural_violations"] = len(report.structural_violations)
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


@app.get("/api/schools/{school_id}/check")
def check_input(school_id: str) -> dict:
    """Проверки до запуска: ошибки ввода и предупреждения по нормам."""
    doc, _ = _load(school_id)
    school, problems = _build(doc)
    return {
        "problems": problems,
        "warnings": [] if problems else check_norms(school),
        "stats": {"classes": len(school.classes), "teachers": len(school.teachers),
                  "rooms": len(school.rooms),
                  "hours": sum(item.hours_per_week for item in school.load)},
    }


# ---------------------------------------------------------------- составление

@app.get("/api/rules")
def rules() -> dict:
    defaults = Rules()
    return {
        "rules": [{"key": key, "title": title, "source": RULE_SOURCES.get(key),
                   "default": getattr(defaults, key)} for key, title in RULE_TITLES.items()],
        "presets": [{"name": name, "about": value["about"]} for name, value in PRESETS.items()],
    }


class SolveRequest(BaseModel):
    budget: float = 300
    preset: str = "Поровну"
    rules: dict[str, str] = {}
    pinned: list[dict] | None = None


@app.post("/api/schools/{school_id}/solve")
def solve(school_id: str, body: SolveRequest) -> dict:
    doc, revision = _load(school_id)

    def on_result(job) -> None:
        result = job.result or {}
        if result.get("type") == "result" and result.get("lessons"):
            job.schedule_id = db.save_schedule(
                school_id, revision, result["lessons"],
                {key: result.get(key) for key in ("status", "seconds", "penalty", "relaxed")})

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
        while True:
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
        "report": _report_dict(check(school, lessons)) if not problems else None,
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
    return _report_dict(check(school, lessons_from_dict(body.lessons)))


@app.post("/api/schools/{school_id}/schedules")
def save_edited(school_id: str, body: LessonsBody) -> dict:
    """Сохранить сетку после ручной правки как новую версию."""
    _, revision = _load(school_id)
    return {"id": db.save_schedule(school_id, revision, body.lessons, {"status": "EDITED"})}


@app.post("/api/schools/{school_id}/export.xlsx")
def export_xlsx(school_id: str, body: LessonsBody, anonymize: bool = False) -> Response:
    doc, _ = _load(school_id)
    school, _ = _build(doc)
    data = excel_bytes(school, lessons_from_dict(body.lessons), anonymize=anonymize)
    return Response(data, media_type="application/vnd.openxmlformats-officedocument."
                                     "spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="raspisanie.xlsx"'})


# ---------------------------------------------------------------- интерфейс

WEB_DIST = ROOT / "web" / "dist"
if WEB_DIST.exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str) -> FileResponse:
        file = WEB_DIST / path
        return FileResponse(file if path and file.is_file() else WEB_DIST / "index.html")
