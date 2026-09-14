import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api } from "../api";
import { Button, cx } from "../ui";

// Первый экран. Человек пришёл, чтобы получить расписание своей школы,
// поэтому здесь два действия: открыть свою или посмотреть на примере.
//
// Справа — не картинка и не цифры «было/стало», а кусок самой сетки в момент
// правки: выбранный урок, подсветка «можно / хуже / нельзя» и заметка на полях
// с пунктом нормы. Это и есть то, чем ЛАД отличается от Untis и «Ректора»
// (CLAUDE.md §3.3): нормы РБ и ответ на «почему сюда нельзя» (docs/DESIGN.md §2).
export function SchoolsPage() {
  const [schools, setSchools] = useState<{ id: string; name: string; updated_at: number }[]>();
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    api.schools().then(setSchools);
  }, []);

  async function create(fromExample: boolean) {
    setBusy(true);
    const { id } = await api.createSchool("", fromExample);
    navigate(fromExample ? `/s/${id}` : `/s/${id}/data`);
  }

  return (
    <div className="min-h-screen px-4 py-10 md:px-8 md:py-16">
      <div className="mx-auto max-w-6xl">
        <p className="text-heading font-bold tracking-tight">ЛАД</p>

        <div className="mt-10 grid items-center gap-12 lg:mt-16 lg:grid-cols-[1fr_minmax(0,34rem)]">
          <div>
            <h1 className="max-w-xl text-[40px] font-semibold leading-[46px] tracking-tight">
              Расписание школы по санитарным нормам Беларуси
            </h1>
            <p className="mt-5 max-w-prose text-heading font-normal text-ink/80">
              Вносите классы, учителей и нагрузку — система составляет сетку за минуты. Двигаете
              урок руками — сразу видно, куда можно, а куда нельзя и по какому пункту нормы.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Button variant="primary" size="lg" disabled={busy} onClick={() => create(false)}>
                Внести свою школу
              </Button>
              <Button size="lg" disabled={busy} onClick={() => create(true)}>
                Открыть пример на 24 класса
              </Button>
            </div>
          </div>

          <GridFragment />
        </div>

        {/* Путь — настоящая последовательность, поэтому с номерами. */}
        <ol className="mt-16 grid gap-6 border-t border-rule pt-8 sm:grid-cols-2 lg:grid-cols-4">
          {[
            ["Данные", "Классы, кабинеты и черновик нагрузки — из типового учебного плана. Учителя — списком из Excel."],
            ["Составление", "Законная сетка — за секунды, дальше система убирает окна у учителей."],
            ["Правка", "Каждое «нельзя» — с причиной словами и пунктом ССЭТ или СанПиН."],
            ["Замены", "Учитель заболел — кто проведёт его уроки, и лист замен на печать."],
          ].map(([title, text], n) => (
            <li key={title} className="flex gap-3">
              <span className="text-small text-pencil">{n + 1}</span>
              <span>
                <span className="block font-semibold">{title}</span>
                <span className="mt-1 block text-small text-pencil">{text}</span>
              </span>
            </li>
          ))}
        </ol>

        {schools && schools.length > 0 && (
          <section className="mt-16">
            <h2 className="mb-3 text-heading">Ваши школы</h2>
            <ul className="divide-y divide-rule rounded-lg border border-rule bg-sheet">
              {schools.map((s) => (
                <li key={s.id}>
                  <Link to={`/s/${s.id}`}
                        className="flex flex-wrap items-baseline justify-between gap-x-4 px-4 py-3 transition-colors duration-150 hover:bg-paper">
                    <span className="font-medium">{s.name}</span>
                    <span className="text-small text-pencil">
                      изменено {new Date(s.updated_at * 1000).toLocaleString("ru-RU", {
                        day: "numeric", month: "long", hour: "2-digit", minute: "2-digit",
                      })}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </div>
  );
}

// Кусок сетки вторника у 5А в момент правки: завуч выбрал русский язык на 3-м
// уроке и навёл на 1-й. Данные условные, но правило настоящее: трудный предмет
// первым или последним уроком — не чаще раза в неделю в классе (п. 94 ССЭТ № 525),
// а в эту неделю русский у 5А уже стоит первым. Причина и выбранный урок
// обязаны сходиться — знающий человек заметит нестыковку сразу.
const FRAGMENT: { period: number; lesson: string; teacher: string; tint?: "ok" | "worse" | "no" | "source" }[] = [
  { period: 1, lesson: "Матем.", teacher: "Галушко", tint: "no" },
  { period: 2, lesson: "Физ-ра", teacher: "Ульянович", tint: "worse" },
  { period: 3, lesson: "Рус. яз.", teacher: "Лапицкая", tint: "source" },
  { period: 4, lesson: "Биология", teacher: "Зайцева", tint: "ok" },
  { period: 5, lesson: "Ин. яз.", teacher: "Пашкевич / Рабцевич", tint: "no" },
];

function GridFragment() {
  return (
    <div aria-hidden="true" className="flex gap-4 max-sm:flex-col">
      <div className="min-w-0 flex-1 overflow-hidden rounded-lg border border-rule bg-sheet">
        <div className="flex border-b border-rule bg-paper font-narrow text-small font-semibold">
          <span className="w-12 border-r border-rule px-2 py-2" />
          <span className="flex-1 bg-pen-soft px-2 py-2 text-pen">5А</span>
        </div>
        {FRAGMENT.map((row) => (
          <div key={row.period}
               className={cx("flex border-rule font-narrow text-cell", row.period === 1 ? "border-t-2 border-t-ink/20" : "border-t")}>
            <span className="w-12 border-r border-rule bg-paper px-2 py-2">
              {row.period === 1 && <span className="mr-1.5 font-semibold">Вт</span>}
              <span className="text-pencil">{row.period}</span>
            </span>
            <span className={cx("flex-1 px-2 py-1.5",
                                row.tint === "ok" && "bg-ok-soft",
                                row.tint === "worse" && "bg-worse-soft",
                                row.tint === "no" && "bg-no-soft/70",
                                row.tint === "source" && "outline outline-2 -outline-offset-2 outline-pen")}>
              <span className="block font-medium">{row.lesson}</span>
              <span className="block text-pencil">{row.teacher}</span>
            </span>
          </div>
        ))}
      </div>
      <div className="w-full max-w-[15rem] self-center rounded-lg border-2 border-no/50 bg-sheet p-4 text-small max-sm:max-w-none">
        <p className="text-heading text-no">Сюда нельзя</p>
        <p className="mt-2">«Русский язык» встанет первым уроком второй раз за неделю, а трудный предмет на краю дня — не чаще раза</p>
        <p className="mt-1 text-pencil">п. 94 ССЭТ № 525</p>
        <p className="mt-3 text-ok">Биология на 4-м — можно, окон не прибавится</p>
      </div>
    </div>
  );
}
