"use client";

import { useRef } from "react";
import { useInView } from "motion/react";

/** Настоящие ограничения, которые завуч держит в голове одновременно.
 *  Половины из них нет ни в одной таблице: они живут в разговорах.
 *  Порядок разъезда задан вручную, чтобы каша выглядела кашей, а не
 *  равномерной лесенкой. */
const repliki = [
  { text: "Иванова по вторникам не может", rx: 210, ry: 14, rot: -2.2, delay: 0 },
  { text: "Химию нельзя после физкультуры", rx: 34, ry: -11, rot: 1.8, delay: 60 },
  { text: "Спортзал один на двадцать четыре класса", rx: 320, ry: 9, rot: 1.1, delay: 30 },
  { text: "У Петровой методический день в среду", rx: 96, ry: -16, rot: -1.6, delay: 100 },
  { text: "Сидорчук работает ещё в одной школе", rx: 396, ry: 13, rot: 2.4, delay: 140 },
  { text: "Восьмые классы делятся на подгруппы", rx: 12, ry: -9, rot: -1.2, delay: 40 },
  { text: "Первым уроком математику не ставить", rx: 268, ry: 17, rot: 2, delay: 120 },
  { text: "В пятницу седьмого урока быть не должно", rx: 140, ry: -14, rot: -1.9, delay: 80 },
];

export function Problema() {
  const ref = useRef<HTMLDivElement>(null);
  const sobrano = useInView(ref, { once: true, amount: 0.55 });

  return (
    <section className="border-t border-rule bg-sheet py-14 md:py-28">
      <div className="mx-auto max-w-[1400px] px-4 md:px-8">
        <p className="max-w-[20ch] text-3xl font-semibold leading-[1.15] tracking-[-0.02em] text-ink md:text-[44px] md:leading-[1.1]">
          В сентябре расписание ещё переставляют.
        </p>

        <div ref={ref} className="mt-8 overflow-hidden md:mt-12">
          <ul className="space-y-2 md:space-y-3">
            {repliki.map((r) => (
              <li
                key={r.text}
                data-sobrano={sobrano}
                className="replika text-[17px] leading-snug text-pencil md:text-xl"
                style={
                  {
                    "--rx": `${r.rx}px`,
                    "--ry": `${r.ry}px`,
                    "--rrot": `${r.rot}deg`,
                    "--rdelay": `${r.delay}ms`,
                  } as React.CSSProperties
                }
              >
                {r.text}
              </li>
            ))}
          </ul>
        </div>

        <div className="mt-9 grid gap-6 md:grid-cols-2 md:gap-16 lg:max-w-[70%]">
          <p className="text-[17px] leading-relaxed text-pencil">
            Всё это надо совместить одновременно, и половины этих условий нет ни
            в одной таблице. Меняешь один урок — рассыпаются три других.
          </p>
          <p className="text-[17px] leading-relaxed text-pencil">
            На это уходят последние недели августа и первые недели сентября. И
            всё равно получается не идеально: кто-то приезжает в школу ради
            одного урока, у кого-то окно посреди дня.
          </p>
        </div>
      </div>
    </section>
  );
}
