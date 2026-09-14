"""Сквозной путь завуча в настоящем браузере: новая школа → данные → составление →
ручная правка → замены → печать → Excel. Собирает ошибки консоли и ответы ≥ 400.

Прогонять перед каждым показом и перед заморозкой. Сервер — отдельный, с временной
базой, чтобы проверочные школы не попадали в рабочую:

    LAD_DB=/tmp/lad-e2e.sqlite3 .venv/bin/uvicorn server.main:app --port 8765 &
    .venv/bin/python tests/e2e_path.py http://127.0.0.1:8765

Нужны собранный интерфейс (cd web && npm run build) и Playwright с Chromium
(.venv/bin/pip install playwright && .venv/bin/playwright install chromium).

Что этот прогон уже поймал 14.09.2026: мастер кабинетов заводил по одному
спецкабинету «на глаз», и путь «жму кнопки по порядку» собирал нерешаемую школу
(труду и информатике не хватало кабинетов); кнопка заведения кабинетов нажималась
раньше, чем приходил расчёт."""
import re
import sys
import tempfile
import time

from playwright.sync_api import expect, sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765"
SHOTS = f"{tempfile.gettempdir()}/lad-e2e"  # скриншоты шагов и падения
TEACHERS = ["Алексеева А. А.", "Борисов Б. Б.", "Васильева В. В.", "Григорьев Г. Г.", "Данилова Д. Д.",
            "Егоров Е. Е.", "Жукова Ж. Ж.", "Зуев З. З.", "Ильина И. И.", "Козлов К. К.",
            "Лебедева Л. Л.", "Морозов М. М."]

console, bad = [], []
passed = False
t0 = time.monotonic()


def log(msg):
    print(f"[{time.monotonic() - t0:6.1f}s] {msg}", flush=True)


def step_nav(page, title):
    page.get_by_role("navigation", name="Шаги ввода").get_by_role("button", name=re.compile(title)).click()


with sync_playwright() as p:
    browser = p.chromium.launch()
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, accept_downloads=True)
    page = ctx.new_page()
    page.set_default_timeout(20_000)
    page.on("console", lambda m: m.type == "error" and console.append(m.text))
    page.on("pageerror", lambda e: console.append(f"pageerror: {e}"))
    page.on("response", lambda r: r.status >= 400 and bad.append((r.status, r.request.method, r.url)))
    try:
        page.goto(BASE)
        page.get_by_role("button", name="Внести свою школу").click()
        page.wait_for_url(re.compile(r"/s/\w+/data"))
        school_url = page.url.split("/data")[0]
        log(f"школа создана: {school_url}")

        page.get_by_label("Название школы").fill("Проверочная школа № 1")
        page.get_by_text("Сохранено").wait_for()
        log("название сохранено")

        step_nav(page, "Классы")
        page.get_by_label("Классов в 5-й параллели").fill("2")
        page.get_by_label("Классов в 6-й параллели").fill("2")
        page.get_by_role("button", name=re.compile(r"^Завести \d+ класс")).click()
        expect(page.locator("table tbody tr")).to_have_count(4)
        log("классы: 4")

        step_nav(page, "Кабинеты")
        page.get_by_role("button", name="Завести кабинеты").click()
        page.locator("table tbody tr").first.wait_for()
        log(f"кабинеты: {page.locator('table tbody tr').count()}")

        step_nav(page, "Предметы")
        page.get_by_role("button", name="Взять предметы из типового плана").click()
        page.get_by_text(re.compile("Добавлено предметов")).wait_for()
        log(f"предметы: {page.locator('table tbody tr').count()}")

        step_nav(page, "Учителя")
        page.locator("textarea").fill("\n".join(TEACHERS))
        page.get_by_role("button", name=f"Добавить учителей: {len(TEACHERS)}").click()
        expect(page.locator("table tbody tr")).to_have_count(len(TEACHERS))
        page.get_by_text("Сохранено").wait_for()
        log("учителя: 12")

        step_nav(page, "Нагрузка")
        page.get_by_role("button", name="Составить черновик нагрузки по плану").click()
        page.get_by_text(re.compile(r"Назначено \d+ из \d+")).wait_for()
        page.screenshot(path=f"{SHOTS}-load.png")
        subjects = page.locator("button span[title]").evaluate_all("els => els.map(e => e.title)")
        log(f"нагрузка: предметов {len(subjects)}")

        def row_index(teacher):
            return page.evaluate("""t => [...document.querySelectorAll('ul.space-y-5 > li')]
                                    .findIndex(li => li.querySelector('select').value === t)""", teacher)

        def assign(teacher, labels):
            # новая строка — последняя; выбрали учителя — щёлкаем свободные клетки по одной
            new_row = page.locator("ul.space-y-5 > li").last
            new_row.locator("select").select_option(teacher)
            for label in labels:
                idx = row_index(teacher)
                row = page.locator("ul.space-y-5 > li").nth(idx)
                chip = row.get_by_role("button", name=label, exact=True)
                with page.expect_response(lambda r: "/load/assign" in r.url):
                    chip.click()

        k = 0
        for subject in subjects:
            page.locator(f'button:has(span[title="{subject}"])').click()
            page.get_by_role("heading", name=subject, exact=True).wait_for()
            chips = page.locator("ul.space-y-5 > li").last.locator("button[aria-pressed]").evaluate_all(
                "els => els.map(e => e.querySelector('span').textContent)")
            first = [c for c in chips if not c.endswith("(2)")]
            second = [c for c in chips if c.endswith("(2)")]
            assign(TEACHERS[k % len(TEACHERS)], first)
            if second:
                assign(TEACHERS[(k + 1) % len(TEACHERS)], second)
            k += 2
        text = page.get_by_text(re.compile(r"Назначено \d+ из \d+")).inner_text()
        log(f"нагрузка назначена: {text}")
        page.screenshot(path=f"{SHOTS}-load-done.png")

        page.get_by_role("link", name="Составление").click()
        page.get_by_text(re.compile(r"\d+ классов, \d+ учителей")).wait_for()
        problems = page.get_by_text("Сначала исправьте данные")
        if problems.count():
            page.screenshot(path=f"{SHOTS}-problems.png", full_page=True)
            raise AssertionError("проверка данных нашла проблемы: " + page.locator("[role=alert]").inner_text())
        page.get_by_role("button", name="Составить расписание").click()
        page.get_by_text(re.compile("Найдено вариантов")).wait_for(timeout=90_000)
        log("первая сетка найдена")
        time.sleep(8)
        page.get_by_role("button", name="Остановить и взять лучшее").click()
        page.wait_for_url(re.compile("/schedule$"), timeout=60_000)
        page.locator("table tbody td div").first.wait_for()
        summary = page.locator("header p").first.inner_text()
        log(f"расписание: {summary}")
        page.screenshot(path=f"{SHOTS}-schedule.png")

        cell = page.locator("table tbody td:has(div)").first
        cell.click()
        page.get_by_text(re.compile("Куда можно поставить|некуда переставить")).wait_for()
        options = page.locator("aside ul li button")
        if options.count():
            options.first.click()
            page.get_by_text("Уроки поменялись местами").wait_for()
            page.get_by_role("button", name="Сохранить версию").click()
            page.get_by_role("button", name="Версия сохранена").wait_for()
            log("ручной ход сделан и сохранён")
        else:
            log("у первого урока нет вариантов — ход пропущен")

        page.get_by_role("link", name="Замены").click()
        page.get_by_label("Кто отсутствует").select_option(index=1)
        page.get_by_label("Когда").fill("2026-09-15")
        page.get_by_role("button", name="Подобрать замены").click()
        page.get_by_text(re.compile("Лист замен|Замены не нужны")).first.wait_for()
        log(f"замены: уроков {page.locator('ol > li').count()}")
        page.screenshot(path=f"{SHOTS}-subs.png", full_page=True)

        page.goto(f"{school_url}/print?by=teacher")
        page.get_by_text(re.compile(r"\d+ листов A4")).wait_for()
        log(page.get_by_text(re.compile(r"\d+ листов A4")).inner_text())

        page.goto(f"{school_url}/data?step=load")
        with page.expect_download() as dl:
            page.get_by_role("button", name="Скачать в Excel").click()
        log(f"Excel скачан: {dl.value.suggested_filename}")
        print(f"\nOK: путь пройден целиком (скриншоты: {SHOTS}-*.png)")
        passed = True
    except Exception as error:  # noqa: BLE001
        page.screenshot(path=f"{SHOTS}-fail.png", full_page=True)
        print(f"\nFAIL: {type(error).__name__}: {str(error)[:600]}\nURL: {page.url}")
    finally:
        print("console errors:", console[:10])
        print("responses >= 400:", bad[:10])
        browser.close()

# Код выхода — чтобы проверку перед показом можно было запускать одной командой.
sys.exit(0 if passed and not console and not bad else 1)
