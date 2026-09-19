export function Kontakt() {
  return (
    <section className="tetrad pole">
      <div className="mx-auto max-w-[1400px] px-4 py-16 md:px-8 md:py-32">
        <div className="mx-auto max-w-[44ch] text-center">
          <h2 className="text-3xl font-semibold leading-tight tracking-[-0.02em] text-ink md:text-4xl">
            Покажем на вашей школе
          </h2>
          <p className="mt-5 text-[17px] leading-relaxed text-pencil">
            Нужна одна таблица — тарификация за этот год. Остальное соберём
            сами и вернём готовую сетку.
          </p>
          {/* Одна главная кнопка на экран (docs/DESIGN.md §2). Почта рядом
              с ней такой же плашкой смотрелась дёшево и спорила за внимание,
              поэтому она ссылкой. */}
          <div className="mt-8">
            <a
              href="https://t.me/nekivlad"
              className="inline-block rounded bg-pen px-7 py-3.5 text-[15px] font-semibold text-white transition-transform duration-150 hover:bg-pen-strong active:translate-y-px"
            >
              Написать в Telegram
            </a>
            <p className="mt-5 text-[15px] text-pencil">
              или на почту{" "}
              <a
                href="mailto:vladbelous0710@gmail.com"
                className="break-all text-pen underline decoration-pen/30 underline-offset-4 transition-colors duration-150 hover:decoration-pen"
              >
                vladbelous0710@gmail.com
              </a>
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
