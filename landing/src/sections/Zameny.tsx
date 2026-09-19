export function Zameny() {
  return (
    <section className="mx-auto max-w-[1400px] px-4 py-20 md:px-8 md:py-28">
      <div className="grid items-start gap-10 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)] lg:gap-20">
        <div className="order-2 lg:order-1">
          <div className="rounded-lg border border-rule bg-sheet p-6 md:p-8">
            <div className="text-[13px] text-pencil">Понедельник, 2-й урок</div>
            <div className="mt-1 text-[17px] font-semibold text-ink">
              7«Б», физика. Учитель на больничном.
            </div>
            <ul className="mt-6 space-y-3">
              <Option
                who="Ковалевская Т. П."
                why="физик, свободна, уже в школе на этом уроке"
                tone="ok"
              />
              <Option
                who="Сидорчук А. В."
                why="физик, свободен, но приедет в школу ради одного урока"
                tone="worse"
              />
              <Option
                who="Раткевич И. Н."
                why="свободна, но ведёт другой предмет"
                tone="worse"
              />
            </ul>
          </div>
        </div>

        <div className="order-1 lg:order-2 lg:pt-4">
          <h2 className="max-w-[16ch] text-3xl font-semibold leading-tight tracking-[-0.02em] text-ink md:text-4xl">
            Замены болят каждый день
          </h2>
          <p className="mt-5 text-[17px] leading-relaxed text-pencil">
            Собрать расписание в августе — это раз в год. Разруливать замены
            приходится каждое утро, и завучи говорят, что вторая боль больше
            первой.
          </p>
          <p className="mt-4 text-[17px] leading-relaxed text-pencil">
            Система предлагает варианты за секунды и рядом с каждым пишет цену:
            кто уже в школе, кому придётся приехать ради одного урока, кто
            свободен, но не ведёт этот предмет.
          </p>
        </div>
      </div>
    </section>
  );
}

function Option({
  who,
  why,
  tone,
}: {
  who: string;
  why: string;
  tone: "ok" | "worse";
}) {
  return (
    <li className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-t border-rule pt-3">
      <span className="text-[15px] font-medium text-ink">{who}</span>
      <span
        className={`rounded px-2 py-0.5 text-[13px] ${
          tone === "ok" ? "bg-ok-soft text-ok" : "bg-worse-soft text-worse"
        }`}
      >
        {tone === "ok" ? "можно" : "можно, но хуже"}
      </span>
      <span className="w-full text-[13px] leading-5 text-pencil">{why}</span>
    </li>
  );
}
