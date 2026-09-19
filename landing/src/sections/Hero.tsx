import { ScheduleGrid } from "@/components/ScheduleGrid";

export function Hero() {
  return (
    <section className="tetrad pole">
      <div className="mx-auto max-w-[1400px] px-4 pt-8 pb-14 md:px-8 md:pt-20 md:pb-28">
        <div className="grid items-center gap-7 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:gap-16">
          <div>
            {/* Перенос задан вручную: иначе заголовок расползается на четыре
                строки и зачёркивание теряется в середине. */}
            <h1 className="text-[32px] font-semibold leading-[1.12] tracking-[-0.02em] text-ink sm:text-4xl md:text-5xl">
              <span className="block">Расписание школы</span>
              за <span className="zacherknuto text-pencil">две недели</span>{" "}
              секунды
            </h1>
            <p className="mt-4 max-w-[46ch] text-[17px] leading-relaxed text-pencil sm:mt-6 sm:text-lg">
              Система ставит уроки с учётом санитарных норм Беларуси и объясняет
              каждое «нельзя», в которое упирается завуч.
            </p>
            <div className="mt-7 flex flex-col items-stretch gap-3 sm:mt-10 sm:flex-row sm:items-center">
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

          {/* Два дня на телефоне, три на широком экране. Сетка тут
              иллюстрация, а не таблица для чтения, и она должна кончаться
              рамкой на границе дня, а не обрывом посреди строки. */}
          <div>
            <ScheduleGrid compact settle days={[2, 3]} />
          </div>
        </div>
      </div>
    </section>
  );
}
