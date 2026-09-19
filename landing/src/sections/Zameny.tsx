"use client";

import { useState } from "react";

/** Три варианта замены и цена каждого. Слова взяты из продукта: «можно»,
 *  «можно, но хуже» — это уровни вердикта, один словарь от солвера до
 *  пикселя (docs/DESIGN.md §3). */
const varianty = [
  {
    who: "Ковалевская Т. П.",
    tone: "ok" as const,
    why: "физик, свободна, уже в школе на этом уроке",
    cena: "Ничего не меняется. Учитель уже здесь, урок идёт по расписанию.",
  },
  {
    who: "Сидорчук А. В.",
    tone: "worse" as const,
    why: "физик, свободен, но приедет в школу ради одного урока",
    cena: "Выход в школу ради одного урока. Считается, но лучше оставить про запас.",
  },
  {
    who: "Раткевич И. Н.",
    tone: "worse" as const,
    why: "свободна, но ведёт другой предмет",
    cena: "Физику не проведёт. Подходит, если нужно просто занять класс.",
  },
];

export function Zameny() {
  const [vybran, setVybran] = useState(0);

  return (
    <section className="tetrad pole">
      <div className="mx-auto max-w-[1400px] px-4 py-14 md:px-8 md:py-28">
        <div className="grid items-start gap-7 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)] lg:gap-20">
          <div className="order-2 lg:order-1">
            <div className="rounded-lg border border-rule bg-sheet p-5 sm:p-6 md:p-8">
              <div className="text-[13px] text-pencil">Понедельник, 2-й урок</div>
              <div className="mt-1 text-[17px] font-semibold text-ink">
                7«Б», физика. Учитель на больничном.
              </div>

              <ul className="mt-5 space-y-1.5">
                {varianty.map((v, i) => {
                  const aktiven = i === vybran;
                  return (
                    <li key={v.who}>
                      <button
                        type="button"
                        onClick={() => setVybran(i)}
                        aria-pressed={aktiven}
                        className={`w-full rounded border px-3 py-3 text-left transition-colors duration-150 ${
                          aktiven
                            ? "border-pen bg-pen-soft"
                            : "border-transparent hover:border-rule"
                        }`}
                      >
                        <span className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                          <span className="text-[15px] font-medium text-ink">
                            {v.who}
                          </span>
                          <span
                            className={`rounded px-2 py-0.5 text-[13px] ${
                              v.tone === "ok"
                                ? "bg-ok-soft text-ok"
                                : "bg-worse-soft text-worse"
                            }`}
                          >
                            {v.tone === "ok" ? "можно" : "можно, но хуже"}
                          </span>
                          <span className="w-full text-[13px] leading-5 text-pencil">
                            {v.why}
                          </span>
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>

              <div className="mt-5 border-t border-rule pt-4">
                <div className="text-[13px] text-pencil">Что будет</div>
                <p className="mt-1 text-[15px] leading-relaxed text-ink">
                  {varianty[vybran].cena}
                </p>
              </div>
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
              Система предлагает варианты за секунды и рядом с каждым пишет
              цену. Выберите любой слева, чтобы увидеть, чем он обойдётся.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
