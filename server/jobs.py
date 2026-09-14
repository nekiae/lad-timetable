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
        from lad.solve import PRESETS, Rules, Weights, assign_rooms, solve
        from lad.storage import lessons_from_dict, lessons_to_dict
        from lad.tables import build_school, tables_from_dict

        school, problems = build_school(tables_from_dict(doc), doc.get("settings") or {},
                                        doc.get("wishes"))
        if problems:
            events.put({"type": "problems", "problems": problems})
            return

        preset = PRESETS.get(options.get("preset") or "Поровну", PRESETS["Поровну"])
        weights = Weights(**options["weights"]) if options.get("weights") else preset["weights"]
        known = set(Rules.__dataclass_fields__)
        rules = Rules(**{k: v for k, v in (options.get("rules") or {}).items() if k in known})
        pinned = lessons_from_dict(options["pinned"]) if options.get("pinned") else None

        def on_progress(snapshot) -> None:
            events.put({"type": "progress", **asdict(snapshot), "gap": snapshot.gap})

        started = time.monotonic()
        result = solve(school, max_seconds=float(options.get("budget") or 300),
                       weights=weights, rules=rules, pinned=pinned,
                       on_progress=on_progress, should_stop=stop_flag.is_set)
        lessons = assign_rooms(school, result.lessons) if result.ok else []
        events.put({
            "type": "result",
            "status": result.status,
            "seconds": time.monotonic() - started,
            "penalty": result.penalty,
            "relaxed": result.relaxed,
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

        Сначала вежливо: солвер вернёт то, что успел. Если через 10 секунд
        процесс ещё жив — завершаем принудительно.
        """
        self._stop.set()

        def kill_later() -> None:
            time.sleep(10)
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
