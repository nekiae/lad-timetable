export function Kontakt() {
  return (
    <section className="tetrad pole">
      <div className="mx-auto max-w-[1400px] px-4 py-16 md:px-8 md:py-32">
      <div className="mx-auto max-w-[44ch] text-center">
        <h2 className="text-3xl font-semibold leading-tight tracking-[-0.02em] text-ink md:text-4xl">
          Покажем на вашей школе
        </h2>
        <p className="mt-5 text-[17px] leading-relaxed text-pencil">
          Нужна одна таблица — тарификация за этот год. Остальное соберём сами и
          вернём готовую сетку.
        </p>
        <div className="mt-9 flex flex-col items-stretch gap-3 sm:mt-10 sm:flex-row sm:flex-wrap sm:items-center sm:justify-center">
          <a
            href="https://t.me/nekivlad"
            className="rounded bg-pen px-5 py-3 text-center text-[15px] font-semibold text-white transition-transform duration-150 hover:bg-pen-strong active:translate-y-px"
          >
            Написать в Telegram
          </a>
          <a
            href="mailto:vladbelous0710@gmail.com"
            className="break-all rounded border border-rule bg-sheet px-5 py-3 text-center text-[15px] font-medium text-ink transition-colors duration-150 hover:border-pen hover:text-pen"
          >
            vladbelous0710@gmail.com
          </a>
        </div>
      </div>
      </div>
    </section>
  );
}
