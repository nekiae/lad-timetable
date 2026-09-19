import { ScheduleGrid } from "@/components/ScheduleGrid";

export function Hero() {
  return (
    <section className="mx-auto max-w-[1400px] px-4 pt-16 pb-20 md:px-8 md:pt-24 md:pb-28">
      <div className="grid items-center gap-12 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:gap-16">
        <div>
          <h1 className="max-w-[12ch] text-4xl font-semibold leading-[1.05] tracking-[-0.02em] text-ink md:text-5xl lg:text-6xl">
            Расписание школы за секунды
          </h1>
          <p className="mt-6 max-w-[46ch] text-lg leading-relaxed text-pencil">
            Система ставит уроки с учётом санитарных норм Беларуси и объясняет
            каждое «нельзя», в которое упирается завуч.
          </p>
          <div className="mt-10 flex flex-wrap items-center gap-3">
            <a
              href="https://t.me/nekivlad"
              className="rounded bg-pen px-5 py-3 text-[15px] font-semibold text-white transition-transform duration-150 hover:bg-pen-strong active:translate-y-px"
            >
              Написать в Telegram
            </a>
            <a
              href="#sborka"
              className="rounded border border-rule bg-sheet px-5 py-3 text-[15px] font-medium text-ink transition-colors duration-150 hover:border-pen hover:text-pen"
            >
              Посмотреть, как собирается
            </a>
          </div>
        </div>

        <div className="relative">
          <ScheduleGrid compact />
          {/* Сетка в герое обрезается снизу: она иллюстрация, а не таблица
              для чтения. Полный размер живёт в секции сборки. */}
          <div className="pointer-events-none absolute inset-x-0 bottom-0 h-24 bg-gradient-to-t from-paper to-transparent" />
        </div>
      </div>
    </section>
  );
}
