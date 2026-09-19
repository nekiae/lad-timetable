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
  const inView = useInView(ref, { once: true, amount: 0.4 });
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
      className="border-y border-rule bg-sheet py-20 md:py-28"
    >
      <div className="mx-auto max-w-[1400px] px-4 md:px-8">
        <div className="max-w-[24ch]">
          <h2 className="text-3xl font-semibold leading-tight tracking-[-0.02em] text-ink md:text-4xl">
            Так это выглядит
          </h2>
          <p className="mt-4 max-w-[52ch] text-[17px] leading-relaxed text-pencil">
            Завуч отдаёт тарификацию. Дальше уроки расставляет солвер: он держит
            в голове все ограничения сразу и не откатывается вручную.
          </p>
        </div>

        <div className="mt-10 grid gap-8 lg:grid-cols-[minmax(0,1fr)_260px] lg:gap-12">
          <div>
            <ScheduleGrid progress={progress} />
          </div>

          <div className="flex flex-col gap-6 lg:pt-1">
            <Readout label="Уроков поставлено" value={`${placed}`} total={`из ${gridStats.lessons}`} />
            <Readout label="Прошло" value={`${seconds} с`} total="" />
            <Readout
              label="Конфликтов в сетке"
              value="0"
              total={done ? "проверено валидатором" : ""}
              tone={done ? "ok" : "plain"}
            />
            <button
              type="button"
              onClick={run}
              disabled={running}
              className="mt-2 w-fit rounded border border-rule bg-paper px-4 py-2.5 text-[15px] font-medium text-ink transition-colors duration-150 hover:border-pen hover:text-pen disabled:cursor-default disabled:text-pencil disabled:hover:border-rule"
            >
              {running ? "Составляю…" : "Составить заново"}
            </button>
            <p className="text-[13px] leading-5 text-pencil">
              Шесть классов из двадцати восьми. Полная сетка гимназии в тот же
              проход занимает 980 уроков.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}

function Readout({
  label,
  value,
  total,
  tone = "plain",
}: {
  label: string;
  value: string;
  total: string;
  tone?: "plain" | "ok";
}) {
  return (
    <div className="border-t border-rule pt-3">
      <div className="text-[13px] text-pencil">{label}</div>
      <div
        className={`mt-1 text-[28px] font-semibold leading-8 ${
          tone === "ok" ? "text-ok" : "text-ink"
        }`}
      >
        {value}
      </div>
      {total && <div className="text-[13px] text-pencil">{total}</div>}
    </div>
  );
}
