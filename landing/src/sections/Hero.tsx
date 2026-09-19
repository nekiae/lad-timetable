import { ScheduleGrid } from "@/components/ScheduleGrid";

export function Hero() {
  return (
    <section className="tetrad pole">
      <div className="mx-auto max-w-[1400px] px-4 pt-14 pb-20 md:px-8 md:pt-20 md:pb-28">
        <div className="grid items-center gap-12 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:gap-16">
          <div>
            {/* Перенос задан вручную: иначе заголовок расползается на четыре
                строки и зачёркивание теряется в середине. */}
            <h1 className="text-[32px] font-semibold leading-[1.12] tracking-[-0.02em] text-ink sm:text-4xl md:text-5xl">
              <span className="block">Расписание школы</span>
              за <span className="zacherknuto text-pencil">две недели</span>{" "}
              секунды
            </h1>
            <p className="mt-5 max-w-[46ch] text-[17px] leading-relaxed text-pencil sm:mt-6 sm:text-lg">
              Система ставит уроки с учётом санитарных норм Беларуси и объясняет
              каждое «нельзя», в которое упирается завуч.
            </p>
            <div className="mt-8 flex flex-col items-stretch gap-3 sm:mt-10 sm:flex-row sm:items-center">
              <a
                href="https://t.me/nekivlad"
                className="rounded bg-pen px-5 py-3 text-center text-[15px] font-semibold text-white transition-transform duration-150 hover:bg-pen-strong active:translate-y-px"
              >
                Написать в Telegram
              </a>
              <a
                href="#sborka"
                className="rounded border border-rule bg-sheet px-5 py-3 text-center text-[15px] font-medium text-ink transition-colors duration-150 hover:border-pen hover:text-pen"
              >
                Посмотреть, как собирается
              </a>
            </div>
          </div>

          <div className="relative max-h-[420px] overflow-hidden lg:max-h-[560px]">
            <ScheduleGrid compact settle />
            {/* Сетка в герое обрезается снизу: она иллюстрация, а не таблица
                для чтения. Полный размер живёт в секции сборки. */}
            <div className="pointer-events-none absolute inset-x-0 bottom-0 h-24 bg-gradient-to-t from-paper to-transparent" />
          </div>
        </div>
      </div>
    </section>
  );
}
