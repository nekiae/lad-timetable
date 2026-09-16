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
WIDE = {"width": 1440, "height": 900}


def hide_names(page) -> None:
    box = page.get_by_label("Скрыть ФИО учителей")
    if box.count():
        box.first.check()
        page.wait_for_timeout(500)


def shoot(school: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport=WIDE, device_scale_factor=2)

        # 1. Готовая неделя школы.
        page.goto(f"{BASE}/s/{school}/schedule")
        page.wait_for_load_state("networkidle")
        hide_names(page)
        page.wait_for_timeout(800)
        page.screenshot(path=str(OUT / "1-grid.png"))

        # 2. Щелчок по первому непустому уроку даёт подсветку недели,
        #    наведение на красную клетку — причину с пунктом нормы.
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

        # 3. Трудность по дням — то, что норм не нарушает, но заметно классу.
        page.keyboard.press("Escape")
        page.wait_for_timeout(400)
        difficulty = page.get_by_role("button", name="Трудность по дням")
        if difficulty.count():
            difficulty.first.click()
            page.wait_for_timeout(1200)
            page.screenshot(path=str(OUT / "3-difficulty.png"))

        # 4. Ввод данных. Снимается шаг «Классы», а не «Нагрузка»: на экране
        #    нагрузки стоят настоящие ФИО, а переключателя «Скрыть ФИО» там нет,
        #    и лист с ними уходить наружу не должен (§8.4).
        page.goto(f"{BASE}/s/{school}/data?step=classes")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(900)
        page.screenshot(path=str(OUT / "4-data.png"))

        # 5. «Что если» — проверка решения до того, как его принять.
        page.goto(f"{BASE}/s/{school}/whatif")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(900)
        page.screenshot(path=str(OUT / "5-whatif.png"))

        # 6. Замены занимают верхнюю половину экрана — окно ниже, по содержимому.
        page.set_viewport_size({"width": 1440, "height": 620})
        page.goto(f"{BASE}/s/{school}/substitutions")
        page.wait_for_load_state("networkidle")
        hide_names(page)
        page.wait_for_timeout(600)
        page.screenshot(path=str(OUT / "6-substitutions.png"))

        # 7. Готовый результат: листы на печать.
        page.set_viewport_size(WIDE)
        page.goto(f"{BASE}/s/{school}/print")
        page.wait_for_load_state("networkidle")
        hide_names(page)
        page.wait_for_timeout(900)
        page.screenshot(path=str(OUT / "7-print.png"))
        browser.close()
    print("снято в", OUT)
    for f in sorted(OUT.glob("*.png")):
        print(" ", f.name)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("нужен id школы с готовым расписанием: tools/summary_shots.py <id>")
    shoot(sys.argv[1])
