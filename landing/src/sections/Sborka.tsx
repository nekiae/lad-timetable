"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useInView, useReducedMotion } from "motion/react";
import { ScheduleGrid, gridStats } from "@/components/ScheduleGrid";

/** Сколько длится показ сборки. Настоящая первая сетка на школе в 24 класса
 *  собирается за 1,6-2,8 с; здесь мы показываем тот же порядок величины,
 *  а не имитируем более быстрый результат. */
const DURATION_MS = 2400;
const STEP_MS = 40;

export function Sborka() {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, amount: 0.15 });
  const reduce = useReducedMotion();

  const [progress, setProgress] = useState(0);
  const [running, setRunning] = useState(false);
  const [done, setDone] = useState(false);

  const run = useCallback(() => {
    if (reduce) {
      setProgress(1);
      setDone(true);
      return;
    }
    setProgress(0);
    setDone(false);
    setRunning(true);
  }, [reduce]);

  useEffect(() => {
    if (inView && progress === 0 && !running && !done) run();
  }, [inView, progress, running, done, run]);

  useEffect(() => {
    if (!running) return;
    const started = Date.now();
    const id = window.setInterval(() => {
      const elapsed = Date.now() - started;
      const next = Math.min(elapsed / DURATION_MS, 1);
      setProgress(next);
      if (next >= 1) {
        setRunning(false);
        setDone(true);
      }
    }, STEP_MS);
    return () => window.clearInterval(id);
  }, [running]);

  const placed = Math.round(gridStats.lessons * progress);
  const seconds = (progress * (DURATION_MS / 1000)).toFixed(1);

  return (
    <section
      id="sborka"
      ref={ref}
      className="scroll-mt-16 border-y border-rule bg-sheet py-20 md:py-28"
    >
      <div className="mx-auto max-w-[1400px] px-4 md:px-8">
        <div>
          <h2 className="max-w-[20ch] text-3xl font-semibold leading-tight tracking-[-0.02em] text-ink md:text-4xl">
            Так это выглядит
          </h2>
          <p className="mt-4 max-w-[52ch] text-[17px] leading-relaxed text-pencil">
            Завуч отдаёт тарификацию. Дальше уроки расставляет солвер: он держит
            в голове все ограничения сразу и не откатывается вручную.
          </p>
        </div>

        {/* На телефоне панель стоит над сеткой: иначе пока идёт сборка,
            секундомер остаётся за нижним краем экрана и весь смысл секции
            проходит мимо. На широком экране она уходит вправо. */}
        <div className="mt-10 grid gap-8 lg:grid-cols-[minmax(0,1fr)_280px] lg:gap-12">
          <div className="order-1 lg:order-2 lg:pt-1">
            <div className="border-t-2 border-ink pt-4">
              <div className="text-[13px] text-pencil">Прошло</div>
              <div className="mt-1 flex items-baseline gap-2">
                <span className="text-[64px] font-semibold leading-[0.9] tracking-[-0.03em] text-ink tabular-nums md:text-[76px]">
                  {seconds}
                </span>
                <span className="text-[22px] font-medium text-pencil">с</span>
              </div>
            </div>

            <div className="mt-7 grid grid-cols-2 gap-x-6 gap-y-5 lg:grid-cols-1 lg:gap-6">
              <Readout
                label="Уроков поставлено"
                value={`${placed}`}
                note={`из ${gridStats.lessons}`}
              />
              <Readout
                label="Конфликтов в сетке"
                value="0"
                note={done ? "проверено валидатором" : ""}
                tone={done ? "ok" : "plain"}
              />
              <button
                type="button"
                onClick={run}
                disabled={running}
                className="col-span-2 w-full rounded border border-rule bg-paper px-4 py-2.5 text-[15px] font-medium text-ink transition-colors duration-150 hover:border-pen hover:text-pen disabled:cursor-default disabled:text-pencil disabled:hover:border-rule lg:col-span-1 lg:w-fit"
              >
                {running ? "Составляю…" : "Составить заново"}
              </button>
              <p className="col-span-2 text-[13px] leading-5 text-pencil lg:col-span-1">
                Это часть сетки. В гимназии 28 классов и 980 уроков в неделю, и
                они ставятся в тот же проход.
              </p>
            </div>
          </div>

          <div className="order-2 lg:order-1">
            <ScheduleGrid progress={progress} interactive />
          </div>
        </div>
      </div>
    </section>
  );
}

function Readout({
  label,
  value,
  note,
  tone = "plain",
}: {
  label: string;
  value: string;
  note: string;
  tone?: "plain" | "ok";
}) {
  return (
    <div className="border-t border-rule pt-3">
      <div className="text-[13px] text-pencil">{label}</div>
      <div
        className={`mt-1 text-[28px] font-semibold leading-8 tabular-nums ${
          tone === "ok" ? "text-ok" : "text-ink"
        }`}
      >
        {value}
      </div>
      {note && <div className="text-[13px] text-pencil">{note}</div>}
    </div>
  );
}
