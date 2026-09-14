import { useMemo } from "react";

import type { Progress, SearchSetup } from "../api";
import { Stat, cx } from "../ui";

export type Grids = { current: number[][]; previous: number[][] | null };

const NORMS = "Нарушений норм";
const GAPS = "Окна у учителей";

// Что солвер делает прямо сейчас. Внутренние шаги CP-SAT — миллионы в секунду,
// их не покажешь и не поймёшь. Показываем то, что имеет смысл и завучу, и нам
// для прокачки алгоритма: этапы конвейера solve() (законная сетка → ноль
// нарушений норм → удобство), каждое найденное улучшение словами, график
// и саму сетку лучшего решения — какие уроки переставлены с прошлого раза.
export function SearchView({ budget, elapsed, progress, first, timeline, setup, grids }: {
  budget: number;
  elapsed: number;
  progress?: Progress;
  first?: Progress;
  timeline: Progress[];
  setup?: SearchSetup;
  grids?: Grids;
}) {
  const found = timeline.filter((t) => Object.keys(t.metrics).length > 0);
  const hasNorms = found.some((t) => NORMS in t.metrics);
  const firstAt = found[0]?.wall;
  const zeroAt = hasNorms ? found.find((t) => t.metrics[NORMS] === 0)?.wall : firstAt;
  const polishAt = found.find((t) => t.phase === "polish")?.wall;
  const phase = progress?.phase;

  const steps = [
    { title: "Законная сетка", text: "Все часы по местам, без конфликтов", at: firstAt,
      active: firstAt === undefined },
    { title: "Ноль нарушений норм", text: "Санитарные нормы — первым делом", at: zeroAt ?? polishAt,
      active: firstAt !== undefined && zeroAt === undefined && phase !== "polish" },
    { title: "Удобство", text: "Окна учителей, ровные дни, пожелания", at: undefined,
      active: firstAt !== undefined && (phase === "polish" || zeroAt !== undefined) },
  ];

  return (
    <section className="rounded-lg border border-rule bg-sheet p-5">
      <div aria-live="polite">
        <div className="h-1 overflow-hidden rounded-full bg-rule">
          <div className="h-full bg-pen transition-[width] duration-500"
               style={{ width: `${Math.min(100, (elapsed / budget) * 100)}%` }} />
        </div>
        <p className="mt-3 text-small text-pencil">
          {Math.round(elapsed)} с из {budget}. {found.length ? `Найдено решений: ${found.length}.` : "Ищу первую законную сетку…"}
        </p>
      </div>

      {/* Этапы — настоящая последовательность, поэтому номера. */}
      <ol className="mt-5 grid gap-3 sm:grid-cols-3">
        {steps.map((step, n) => {
          const done = step.at !== undefined && !step.active;
          return (
            <li key={step.title}
                className={cx("rounded border px-3 py-2",
                              step.active ? "border-pen bg-pen-soft" : done ? "border-ok/30 bg-ok-soft" : "border-rule")}>
              <p className="flex items-baseline justify-between gap-2">
                <span className={cx("font-semibold", step.active && "text-pen")}>{n + 1}. {step.title}</span>
                <span className="text-small text-pencil">
                  {done ? `${step.at!.toFixed(1)} с` : step.active ? "сейчас" : ""}
                </span>
              </p>
              <p className="text-small text-pencil">{step.text}</p>
              {/* На этапе норм — какая норма сейчас держит: хвост «1 → 0» бывает
                  долгим, и видно, во что упёрся солвер. */}
              {n === 1 && step.active && progress && Object.values(progress.norms ?? {}).some(Boolean) && (
                <ul className="mt-1.5 space-y-0.5 text-small">
                  {Object.entries(progress.norms).filter(([, v]) => v > 0).map(([title, v]) => (
                    <li key={title} className="flex justify-between gap-2">
                      <span>{title}</span><span className="font-semibold text-no">{v}</span>
                    </li>
                  ))}
                </ul>
              )}
            </li>
          );
        })}
      </ol>

      {progress && Object.keys(progress.metrics).length > 0 && (
        <>
          <dl className="mt-5 grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-3">
            {Object.entries(progress.metrics).map(([label, value]) => (
              <Stat key={label} label={label} value={value} was={first?.metrics[label]} />
            ))}
          </dl>
          {/* На этапе черновика цель одна — нормы; окна и ровность дней солвер
              сознательно не трогает, и «1242 окна» без пояснения пугают. */}
          {phase === "draft" && (
            <p className="mt-3 max-w-prose text-small text-pencil">
              Окна учителей и ровность дней пока не в приоритете — они пойдут вниз на 3-м этапе, когда нормы будут закрыты.
            </p>
          )}
        </>
      )}

      {found.length > 0 && (
        <div className="mt-6 grid gap-6 md:grid-cols-[auto_1fr]">
          {setup && grids && <LiveGrid setup={setup} grids={grids} />}
          <div className="min-w-0 space-y-5">
            <Chart timeline={found} elapsed={elapsed} />
            <Log timeline={found} />
          </div>
        </div>
      )}
    </section>
  );
}

// Сетка лучшего решения. Столбцы — классы, строки — уроки, блоки — дни.
// Серым — урок стоит, синим — урок сюда переставлен с прошлого снимка.
function LiveGrid({ setup, grids }: { setup: SearchSetup; grids: Grids }) {
  const { occupied, changed, moved } = useMemo(() => {
    const column = new Map(setup.class_ids.map((id, i) => [id, i]));
    const cells = (grid: number[][], only?: Set<string>) => {
      const out = new Set<string>();
      for (const [i, d, p] of grid) {
        if (only && !only.has(`${i}|${d}|${p}`)) continue;
        for (const c of setup.load[i]?.classes ?? []) out.add(`${column.get(c)}|${d}|${p}`);
      }
      return out;
    };
    const before = new Set((grids.previous ?? []).map(([i, d, p]) => `${i}|${d}|${p}`));
    const fresh = grids.previous
      ? new Set(grids.current.map(([i, d, p]) => `${i}|${d}|${p}`).filter((k) => !before.has(k)))
      : new Set<string>();
    return { occupied: cells(grids.current), changed: cells(grids.current, fresh), moved: fresh.size };
  }, [setup, grids]);

  const cols = setup.class_ids.length;
  return (
    <figure className="w-full max-w-[18rem]">
      <div className="space-y-1.5" role="img"
           aria-label={`Сетка лучшего решения: ${cols} классов, переставлено уроков ${moved}`}>
        {setup.days.map((d) => (
          <div key={d} className="grid gap-px" style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}>
            {Array.from({ length: setup.periods }, (_, p) =>
              Array.from({ length: cols }, (_, c) => {
                const key = `${c}|${d}|${p + 1}`;
                return (
                  <span key={key}
                        className={cx("h-1.5 rounded-[1px] transition-colors duration-700",
                                      changed.has(key) ? "bg-pen" : occupied.has(key) ? "bg-ink/25" : "bg-rule/40")} />
                );
              }))}
          </div>
        ))}
      </div>
      <figcaption className="mt-2 text-small text-pencil">
        Сетка лучшего решения: столбцы — {cols} классов, блоки — дни.
        {grids.previous ? ` Синим — переставлено с прошлого снимка: ${moved} уроков.` : ""}
      </figcaption>
    </figure>
  );
}

// График: нарушения норм (красным — это нарушения) и окна учителей по времени.
// Каждая линия в своём масштабе: важна форма падения, а не абсолютные числа.
function Chart({ timeline, elapsed }: { timeline: Progress[]; elapsed: number }) {
  // Шкала — по прошедшему времени, а не по всему бюджету: иначе первые
  // полминуты, где и происходит главное, сжимаются в левый край графика.
  const span = Math.max(10, elapsed, timeline.at(-1)?.wall ?? 0);
  const series = [
    { key: NORMS, stroke: "stroke-no", swatch: "bg-no" },
    { key: GAPS, stroke: "stroke-ink", swatch: "bg-ink" },
  ].filter((s) => timeline.some((t) => s.key in t.metrics));

  const path = (key: string) => {
    const points = timeline.filter((t) => key in t.metrics);
    const max = Math.max(1, ...points.map((t) => t.metrics[key]));
    const x = (wall: number) => Math.min(100, (wall / span) * 100);
    const y = (v: number) => 38 - (v / max) * 34;
    let d = "";
    points.forEach((t, i) => {
      const px = x(t.wall), py = y(t.metrics[key]);
      d += i === 0 ? `M ${px} ${py}` : ` H ${px} V ${py}`; // ступенькой: значение держится до следующего решения
    });
    const last = points.at(-1);
    return last ? `${d} H ${x(Math.max(elapsed, last.wall))}` : d;
  };

  return (
    <div>
      <svg viewBox="0 0 100 40" preserveAspectRatio="none" className="h-28 w-full rounded border border-rule bg-paper"
           role="img" aria-label="Как менялись нарушения норм и окна учителей">
        {series.map((s) => (
          <path key={s.key} d={path(s.key)} fill="none" strokeWidth={2} vectorEffect="non-scaling-stroke"
                className={s.stroke} />
        ))}
      </svg>
      <p className="mt-1.5 flex flex-wrap gap-x-4 text-small text-pencil">
        {series.map((s) => (
          <span key={s.key} className="inline-flex items-center gap-1.5">
            <span className={cx("inline-block h-0.5 w-3", s.swatch)} />{s.key}
          </span>
        ))}
        <span className="ml-auto">время: 0 — {Math.round(span)} с</span>
      </p>
    </div>
  );
}

// Журнал: что именно стало лучше на каждом найденном решении — словами.
function Log({ timeline }: { timeline: Progress[] }) {
  const lines = useMemo(() => {
    const out: { wall: number; text: string; phase?: boolean }[] = [];
    timeline.forEach((t, n) => {
      const prev = timeline[n - 1];
      if (!prev) {
        out.push({ wall: t.wall, text: "Первая законная сетка найдена", phase: true });
        return;
      }
      if (prev.phase === "draft" && t.phase === "polish")
        out.push({ wall: t.wall, text: "Нормы закрыты, дальше улучшаю удобство", phase: true });
      const better = Object.entries(t.metrics)
        .filter(([k, v]) => prev.metrics[k] !== undefined && v < prev.metrics[k])
        .map(([k, v]) => `${k.toLowerCase()} ${prev.metrics[k]} → ${v}`);
      if (better.length) out.push({ wall: t.wall, text: `Решение ${n + 1}: ${better.join(", ")}` });
    });
    return out.reverse().slice(0, 8);
  }, [timeline]);

  return (
    <table className="w-full text-small">
      <tbody>
        {lines.map((line, i) => (
          <tr key={`${line.wall}-${i}`} className="align-baseline">
            <td className="w-14 py-0.5 pr-3 text-right text-pencil">{line.wall.toFixed(1)} с</td>
            <td className={cx("py-0.5", line.phase ? "font-semibold text-ok" : "text-ink/85")}>{line.text}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
