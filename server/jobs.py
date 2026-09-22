"""Составление расписания в отдельном ПРОЦЕССЕ.

Почему не поток, как в Streamlit (lad/job.py). Три причины:
  1. «Стоп» должен останавливать гарантированно. Поток можно только
     попросить, процесс — завершить.
  2. Падение солвера (нехватка памяти на большой школе) не роняет сервер,
     а с ним — открытые страницы других завучей.
  3. Два запуска не делят один интерпретатор и не мешают друг другу.

Процесс отдаёт наверх снимки хода поиска через очередь; сервер складывает
их в историю задачи, а браузер читает её потоком событий (SSE).
"""

from __future__ import annotations

import multiprocessing as mp
import queue
import threading
import time
import traceback
import uuid
from dataclasses import asdict, dataclass, field

from . import ROOT  # noqa: F401 — кладёт src/ в sys.path и в дочернем процессе

# spawn, а не fork: на macOS fork после загрузки OR-Tools ненадёжен,
# а в Linux-контейнере spawn ведёт себя так же — меньше сюрпризов при деплое.
_CTX = mp.get_context("spawn")


def _worker(doc: dict, options: dict, events, stop_flag) -> None:
    """Тело дочернего процесса: собрать школу, составить, отдать результат."""
    try:
        from lad.solve import (PRESETS, Rules, Targeted, Weights, assign_rooms, solve,
                               weights_from_prefs)
        from lad.storage import lessons_from_dict, lessons_to_dict
        from lad.tables import build_school, tables_from_dict

        school, problems = build_school(tables_from_dict(doc), doc.get("settings") or {},
                                        doc.get("wishes"), doc.get("targeted"))
        if problems:
            events.put({"type": "problems", "problems": problems})
            return

        preset = PRESETS.get(options.get("preset") or "Поровну", PRESETS["Поровну"])
        weights = Weights(**options["weights"]) if options.get("weights") else preset["weights"]
        # Предпочтения школы (ползунки) — поверх весов выбранного режима.
        weights = weights_from_prefs(weights, options.get("prefs"))
        known = set(Rules.__dataclass_fields__)
        rules = Rules(**{k: v for k, v in (options.get("rules") or {}).items() if k in known})
        # Адресные пожелания лежат в данных школы, а не в запросе: это её
        # постоянные договорённости («у одиннадцатых ровные дни жёстко»),
        # а не настройка одного запуска.
        targeted = Targeted(doc.get("targeted") or [])
        pinned = lessons_from_dict(options["pinned"]) if options.get("pinned") else None
        hint = lessons_from_dict(options["hint"]) if options.get("hint") else None
        stay = hint if options.get("keep") else None  # пересборка: двигать нужное, а не всё

        # Справочник для живой сетки в браузере: что за урок стоит за строкой
        # нагрузки i из снимков хода поиска. Отдаётся один раз до начала.
        subjects = {s.id: s.name for s in school.subjects}
        events.put({
            "type": "setup",
            "classes": [c.name for c in school.classes],
            "class_ids": [c.id for c in school.classes],
            "days": sorted(d for d, kind in school.day_kinds.items() if kind.value == "lessons"),
            "periods": school.periods_per_day,
            "load": [{"classes": school.group(item.group_id).class_ids,
                      "subject": subjects.get(item.subject_id, "")} for item in school.load],
        })

        started = time.monotonic()

        def on_progress(snapshot) -> None:
            # wall — от старта задачи. У каждого этапа solve() свой отсчёт seconds
            # с нуля, и график по нему рисовал бы доводку поверх черновика.
            events.put({"type": "progress", **asdict(snapshot), "gap": snapshot.gap,
                        "wall": time.monotonic() - started})

        result = solve(school, max_seconds=float(options.get("budget") or 300),
                       weights=weights, rules=rules, pinned=pinned, hint=hint, stay=stay,
                       on_progress=on_progress, should_stop=stop_flag.is_set,
                       params=options.get("params"), targeted=targeted,
                       settle=float(options["settle"]) if options.get("settle") else None)
        lessons = assign_rooms(school, result.lessons) if result.ok else []
        # Пустой результат без объяснения — худшее, что можно показать завучу:
        # «не находится» не говорит, что чинить. Выясняем причину тем же
        # способом, что и солвер: снимаем нормы и смотрим, дело в них или
        # в арифметике школы.
        why: list[str] = []
        if not lessons and not stop_flag.is_set():
            from lad.solve import diagnose
            why = diagnose(school, rules=rules, max_seconds=20, total_seconds=120)
        events.put({
            "type": "result",
            "status": result.status,
            "seconds": time.monotonic() - started,
            "penalty": result.penalty,
            "relaxed": result.relaxed,
            "why": why,
            "lessons": lessons_to_dict(lessons),
        })
    except BaseException:  # noqa: BLE001 — любую ошибку отдаём наверх текстом
        events.put({"type": "error", "error": traceback.format_exc()})


@dataclass
class Job:
    id: str
    school_id: str
    revision_id: int
    options: dict
    started_at: float = field(default_factory=time.time)
    history: list[dict] = field(default_factory=list)
    result: dict | None = None
    setup: dict | None = None  # справочник для живой сетки (см. _worker)
    schedule_id: str | None = None
    finished: bool = False

    def __post_init__(self) -> None:
        self._events = _CTX.Queue()
        self._stop = _CTX.Event()
        self._process: mp.Process | None = None

    def start(self, doc: dict, on_result) -> None:
        self._process = _CTX.Process(target=_worker, daemon=True,
                                     args=(doc, self.options, self._events, self._stop))
        self._process.start()
        threading.Thread(target=self._drain, args=(on_result,), daemon=True).start()

    def stop(self) -> None:
        """Попросить остановиться и отдать лучшее найденное.

        Сначала вежливо: солвер вернёт то, что успел. Если через 30 секунд
        процесс ещё жив — завершаем принудительно. 10 секунд оказалось мало:
        после остановки ещё раздаются кабинеты и считается отчёт, а убитый
        процесс не отдаёт ничего — завуч терял найденную сетку (15.09.2026).
        """
        self._stop.set()

        def kill_later() -> None:
            time.sleep(30)
            if self._process and self._process.is_alive():
                self._process.terminate()

        threading.Thread(target=kill_later, daemon=True).start()

    def _drain(self, on_result) -> None:
        while True:
            try:
                event = self._events.get(timeout=1.0)
            except queue.Empty:
                if self._process and not self._process.is_alive():
                    if self.result is None:
                        self.result = {"type": "error",
                                       "error": "Процесс составления завершился без ответа"}
                    break
                continue
            if event["type"] == "progress":
                self.history.append(event)
            elif event["type"] == "setup":
                self.setup = event
            else:
                self.result = event
                break
        try:
            on_result(self)
        finally:
            self.finished = True


JOBS: dict[str, Job] = {}


def start_job(school_id: str, revision_id: int, doc: dict, options: dict, on_result) -> Job:
    job = Job(id=uuid.uuid4().hex[:12], school_id=school_id,
              revision_id=revision_id, options=options)
    JOBS[job.id] = job
    job.start(doc, on_result)
    return job
