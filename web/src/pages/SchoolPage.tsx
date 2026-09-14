import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { api, type Progress, type SolveDone } from "../api";

const BUDGETS = [
  { seconds: 120, label: "2 минуты" },
  { seconds: 300, label: "5 минут" },
  { seconds: 600, label: "10 минут" },
];

// Экран школы: что введено, что мешает составить, и кнопка составления
// с живым ходом поиска. Ход показываем величинами, понятными завучу
// («окон у учителей 120 → 36»), а не суммой штрафов.
export function SchoolPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const [check, setCheck] = useState<Awaited<ReturnType<typeof api.check>>>();
  const [presets, setPresets] = useState<{ name: string; about: string }[]>([]);
  const [preset, setPreset] = useState("Поровну");
  const [budget, setBudget] = useState(300);
  const [job, setJob] = useState<string>();
  const [progress, setProgress] = useState<Progress>();
  const [first, setFirst] = useState<Progress>();
  const [done, setDone] = useState<SolveDone>();
  const [elapsed, setElapsed] = useState(0);
  const unwatch = useRef<() => void>();

  useEffect(() => {
    api.check(id).then(setCheck);
    api.rules().then((r) => setPresets(r.presets));
    return () => unwatch.current?.();
  }, [id]);

  useEffect(() => {
    if (!job || done) return;
    const started = Date.now();
    const timer = setInterval(() => setElapsed((Date.now() - started) / 1000), 500);
    return () => clearInterval(timer);
  }, [job, done]);

  async function start() {
    setDone(undefined);
    setProgress(undefined);
    setFirst(undefined);
    const { job_id } = await api.solve(id, { budget, preset });
    setJob(job_id);
    unwatch.current = api.watch(
      job_id,
      (p) => {
        setProgress(p);
        if (Object.keys(p.metrics).length) setFirst((f) => f ?? p);
      },
      (d) => {
        setDone(d);
        if (d.type === "result" && d.schedule_id) navigate(`/s/${id}/schedule`);
      },
    );
  }

  const running = Boolean(job && !done);
  const blocked = Boolean(check?.problems.length);

  return (
    <div className="mx-auto max-w-3xl px-4 py-10 md:px-10">
      <h1 className="text-3xl font-bold tracking-tight">Составление</h1>

      {check && (
        <p className="mt-3 text-ink/80">
          {check.stats.classes} классов, {check.stats.teachers} учителей, {check.stats.rooms} кабинетов,{" "}
          {check.stats.hours} уроков в неделю.
        </p>
      )}

      {blocked && (
        <section className="mt-6 rounded-lg border border-red-pen/40 bg-red-soft p-4">
          <h2 className="font-semibold text-red-pen">Сначала исправьте данные</h2>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
            {check!.problems.slice(0, 12).map((p) => <li key={p}>{p}</li>)}
          </ul>
          {check!.problems.length > 12 && (
            <p className="mt-2 text-sm text-pencil">и ещё {check!.problems.length - 12}</p>
          )}
        </section>
      )}

      {check && check.warnings.length > 0 && (
        <section className="mt-6 rounded-lg border border-warn/30 bg-warn-soft p-4 text-sm">
          <ul className="list-disc space-y-1 pl-5">
            {check.warnings.map((w) => <li key={w}>{w}</li>)}
          </ul>
        </section>
      )}

      <section className="mt-8 grid gap-6 md:grid-cols-2">
        <fieldset disabled={running}>
          <legend className="mb-2 font-semibold">Чьё удобство важнее</legend>
          <div className="space-y-2">
            {presets.map((p) => (
              <label key={p.name}
                     className={`block cursor-pointer rounded-md border px-3 py-2 ${
                       preset === p.name ? "border-pen bg-pen-soft" : "border-rule bg-white"}`}>
                <input type="radio" name="preset" className="sr-only" checked={preset === p.name}
                       onChange={() => setPreset(p.name)} />
                <span className="font-medium">{p.name}</span>
                <span className="mt-0.5 block text-sm text-ink/70">{p.about}</span>
              </label>
            ))}
          </div>
        </fieldset>

        <fieldset disabled={running}>
          <legend className="mb-2 font-semibold">Сколько искать</legend>
          <div className="flex flex-wrap gap-2">
            {BUDGETS.map((b) => (
              <button key={b.seconds} type="button" onClick={() => setBudget(b.seconds)}
                      className={budget === b.seconds ? "btn-primary" : "btn-quiet"}>
                {b.label}
              </button>
            ))}
          </div>
          <p className="mt-3 text-sm text-ink/70">
            Законная сетка появляется за секунды. Остальное время система убирает окна
            и выравнивает дни — чем дольше, тем удобнее.
          </p>
        </fieldset>
      </section>

      <div className="mt-8 flex gap-3">
        {!running ? (
          <button className="btn-primary px-6 py-3 text-base" disabled={blocked || !check} onClick={start}>
            Составить расписание
          </button>
        ) : (
          <button className="btn-quiet px-6 py-3 text-base" onClick={() => job && api.stop(job)}>
            Остановить и взять лучшее
          </button>
        )}
      </div>

      {running && (
        <section className="mt-8 rounded-lg border border-rule bg-white p-5" aria-live="polite">
          <div className="h-1.5 overflow-hidden rounded-full bg-rule">
            <div className="h-full bg-pen transition-[width] duration-500"
                 style={{ width: `${Math.min(100, (elapsed / budget) * 100)}%` }} />
          </div>
          <p className="mt-3 text-sm text-pencil">
            {Math.round(elapsed)} с из {budget}.{" "}
            {progress?.solutions ? `Найдено вариантов: ${progress.solutions}.` : "Ищу первую законную сетку…"}
          </p>
          {progress && Object.keys(progress.metrics).length > 0 && (
            <dl className="mt-4 grid grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-3">
              {Object.entries(progress.metrics).map(([label, value]) => (
                <div key={label}>
                  <dt className="text-sm text-pencil">{label}</dt>
                  <dd className="text-xl font-semibold">
                    {first?.metrics[label] !== undefined && first.metrics[label] !== value && (
                      <span className="mr-2 text-base font-normal text-pencil line-through">
                        {first.metrics[label]}
                      </span>
                    )}
                    {value}
                  </dd>
                </div>
              ))}
            </dl>
          )}
        </section>
      )}

      {done && done.type !== "result" && (
        <section className="mt-8 rounded-lg border border-red-pen/40 bg-red-soft p-4 text-sm">
          {done.type === "problems" && (
            <ul className="list-disc pl-5">{done.problems?.map((p) => <li key={p}>{p}</li>)}</ul>
          )}
          {done.type === "error" && <pre className="whitespace-pre-wrap">{done.error}</pre>}
        </section>
      )}
      {done?.type === "result" && !done.schedule_id && (
        <p className="mt-8 rounded-lg border border-warn/30 bg-warn-soft p-4">
          Расписание с такими данными не находится. Проверьте кабинеты и нагрузку:
          часов не может быть больше, чем уроков в сетке.
        </p>
      )}
    </div>
  );
}
