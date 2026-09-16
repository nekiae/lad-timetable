"""Экраны прототипа для саммари-PDF — снимаются с локального сервера.

    .venv/bin/uvicorn server.main:app --port 8000   # в соседнем окне
    .venv/bin/python tools/summary_shots.py <id школы>

Кладёт png в data/summary/. Обезличивание включается один раз переключателем
в шапке и держится во всех разделах: лист уходит третьим лицам (§8.4).
Школа берётся с готовым расписанием — иначе снимать нечего. Часть кадров живая
(солвер на ходу, подобранные замены), поэтому прогон занимает несколько минут.
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
    """Общий переключатель в шапке. На печати он свой — там та же подпись."""
    for label in ("Скрыть ФИО", "Скрыть ФИО учителей"):
        box = page.get_by_label(label, exact=True)
        if box.count():
            if not box.first.is_checked():
                box.first.check()
                page.wait_for_timeout(500)
            return


def shot(page, name: str) -> None:
    page.screenshot(path=str(OUT / name))
    print("  ", name)


def shoot(school: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport=WIDE, device_scale_factor=2)

        # Обезличивание включается один раз — дальше оно живёт в сессии вкладки.
        page.goto(f"{BASE}/s/{school}/schedule")
        page.wait_for_load_state("networkidle")
        hide_names(page)

        # 1. Солвер на ходу: живые цифры, пока идёт составление.
        page.goto(f"{BASE}/s/{school}")
        page.wait_for_load_state("networkidle")
        start = page.get_by_role("button", name="Составить расписание")
        if start.count():
            start.first.click()
            # Кадр — на 14-й секунде, пока видно торговлю за окна. А останавливать
            # прогон рано нельзя: он перезапишет сохранённую сетку той, где нормы
            # ещё не закрыты, и все остальные кадры уйдут с «нарушений: 1».
            # Ноль нарушений появляется на 19–26-й секунде (STATUS.md), берём запас.
            page.wait_for_timeout(14000)
            shot(page, "1-solving.png")
            page.wait_for_timeout(46000)
            stop = page.get_by_role("button", name="Остановить")
            if stop.count():
                stop.first.click()
                page.wait_for_timeout(5000)

        # 2. Готовая неделя школы.
        page.goto(f"{BASE}/s/{school}/schedule")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(900)
        shot(page, "2-grid.png")

        # 3. Щелчок по уроку — подсветка недели, наведение на красную клетку —
        #    причина с пунктом нормы.
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
        shot(page, "3-highlight.png")

        # 4. Трудность по дням.
        page.keyboard.press("Escape")
        page.wait_for_timeout(400)
        difficulty = page.get_by_role("button", name="Трудность по дням")
        if difficulty.count():
            difficulty.first.click()
            page.wait_for_timeout(1200)
            shot(page, "4-difficulty.png")

        # 5. Замены: подобранные кандидаты на каждый урок.
        page.goto(f"{BASE}/s/{school}/substitutions")
        page.wait_for_load_state("networkidle")
        select = page.locator("select").first
        if select.locator("option").count() > 1:
            select.select_option(index=1)
            page.wait_for_timeout(500)
            pick = page.get_by_role("button", name="Подобрать замены")
            if pick.count():
                pick.first.click()
                page.wait_for_timeout(4000)
        shot(page, "5-substitutions.png")

        # 6. «Что если»: ответ приходит сразу, если изменение невыполнимо.
        page.goto(f"{BASE}/s/{school}/whatif")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1200)
        shot(page, "6-whatif.png")

        # 7. Ввод данных. Шаг «Классы», а не «Нагрузка»: раздел данных не
        #    обезличивается — там завуч работает со своими фамилиями (§8.4).
        page.goto(f"{BASE}/s/{school}/data?step=classes")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(900)
        shot(page, "7-data.png")

        # 8. Шаблон Excel с листом-инструкцией.
        guide = page.get_by_role("button", name="Как оформить Excel")
        if guide.count():
            guide.first.click()
            page.wait_for_timeout(1500)
            shot(page, "8-excel.png")

        # 9. Готовый результат: листы на печать.
        page.goto(f"{BASE}/s/{school}/print")
        page.wait_for_load_state("networkidle")
        hide_names(page)
        page.wait_for_timeout(900)
        shot(page, "9-print.png")
        browser.close()
    print("снято в", OUT)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("нужен id школы с готовым расписанием: tools/summary_shots.py <id>")
    shoot(sys.argv[1])
