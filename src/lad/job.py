"""Составление расписания в фоне — чтобы интерфейс не замирал на десять минут.

Зачем отдельный поток. Поиск идёт минутами, а Streamlit выполняет скрипт
целиком: пока `solve()` не вернётся, страница мертва — ни прогресса, ни
возможности прервать. Поэтому солвер уезжает в поток, а страница читает
его снимки и перерисовывает только блок прогресса.

Поток НИКОГДА не трогает `st.*`: у него нет контекста Streamlit, и вызов
привёл бы к предупреждениям и гонкам. Он только складывает снимки в список,
а рисует их основной поток.
"""

from __future__ import annotations

import threading
import time

from .model import School
from .solve import Progress, Rules, SolveResult, Weights, solve


class SolveJob:
    """Один запуск составления: поток, история снимков, просьба остановиться."""

    def __init__(self, school: School, max_seconds: float,
                 weights: Weights | None = None, rules: Rules | None = None,
                 pinned: list | None = None):
        self.school = school
        self.max_seconds = max_seconds
        self.weights = weights
        self.rules = rules
        self.pinned = pinned

        self.history: list[Progress] = []
        self.result: SolveResult | None = None
        self.error: BaseException | None = None
        self.started_at: float | None = None
        self.elapsed: float = 0.0
        self.stop_requested = False
        self._thread: threading.Thread | None = None

    # --- запуск и остановка

    def start(self) -> None:
        self.started_at = time.monotonic()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def request_stop(self) -> None:
        """Прервать поиск и взять лучшее найденное (а не выбросить работу)."""
        self.stop_requested = True

    # --- состояние для интерфейса

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    @property
    def finished(self) -> bool:
        return bool(self._thread and not self._thread.is_alive())

    @property
    def latest(self) -> Progress | None:
        return self.history[-1] if self.history else None

    @property
    def first_improved(self) -> Progress | None:
        """Первый снимок с метриками — точка отсчёта «было → стало»."""
        for snapshot in self.history:
            if snapshot.metrics:
                return snapshot
        return None

    @property
    def first_scored(self) -> Progress | None:
        """Первый снимок со штрафом — точка отсчёта «насколько стало лучше».

        Не совпадает с `first_improved`: у снимка, которым заканчивается первая
        фаза, метрики уже есть, а штрафа ещё нет — целевая функция добавляется
        в модель только перед второй фазой.
        """
        for snapshot in self.history:
            if snapshot.penalty is not None:
                return snapshot
        return None

    def seconds(self) -> float:
        if self.started_at is None:
            return 0.0
        return self.elapsed or (time.monotonic() - self.started_at)

    # --- поток

    def _run(self) -> None:
        try:
            self.result = solve(
                self.school,
                max_seconds=self.max_seconds,
                weights=self.weights,
                rules=self.rules,
                on_progress=self.history.append,
                should_stop=lambda: self.stop_requested,
                pinned=self.pinned,
            )
        except BaseException as error:  # noqa: BLE001 — показываем завучу как есть
            self.error = error
        finally:
            self.elapsed = time.monotonic() - (self.started_at or time.monotonic())
