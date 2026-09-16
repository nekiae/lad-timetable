"""Экраны прототипа для саммари-PDF — снимаются с локального сервера.

    .venv/bin/uvicorn server.main:app --port 8000   # в соседнем окне
    .venv/bin/python tools/summary_shots.py <id школы>

Кладёт png в data/summary/. Имена учителей везде скрыты: лист уходит третьим
лицам (§8.4). Школа берётся с готовым расписанием — иначе снимать нечего.
"""
from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "summary"
BASE = "http://127.0.0.1:8000"


def hide_names(page) -> None:
    box = page.get_by_label("Скрыть ФИО учителей")
    if box.count():
        box.first.check()
        page.wait_for_timeout(500)


def shoot(school: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=2)

        page.goto(f"{BASE}/s/{school}/schedule")
        page.wait_for_load_state("networkidle")
        hide_names(page)
        page.wait_for_timeout(800)
        page.screenshot(path=str(OUT / "1-grid.png"))

        # Щелчок по первому непустому уроку: он и даёт подсветку недели.
        cells = page.locator("td[data-cell]")
        for i in range(cells.count()):
            if cells.nth(i).inner_text().strip():
                cells.nth(i).click()
                break
        page.wait_for_timeout(1500)
        red = page.locator('td[data-cell][class*="bg-no-soft"]')
        if red.count():
            red.first.hover()
            page.wait_for_timeout(900)
        page.screenshot(path=str(OUT / "2-highlight.png"))

        # Замены занимают верхнюю половину экрана, и в полный рост лист уезжает
        # на третью страницу — поэтому окно ниже, ровно по содержимому.
        page.set_viewport_size({"width": 1440, "height": 620})
        page.goto(f"{BASE}/s/{school}/substitutions")
        page.wait_for_load_state("networkidle")
        hide_names(page)
        page.wait_for_timeout(600)
        page.screenshot(path=str(OUT / "3-substitutions.png"))
        browser.close()
    print("снято в", OUT)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("нужен id школы с готовым расписанием: tools/summary_shots.py <id>")
    shoot(sys.argv[1])
