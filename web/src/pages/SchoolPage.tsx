import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { api, type Progress, type SolveDone } from "../api";
import { Button, Choice, Notice, Panel, Segmented, Stat } from "../ui";

const BUDGETS = [
  { value: 120, label: "2 минуты" },
  { value: 300, label: "5 минут" },
  { value: 600, label: "10 минут" },
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
    <div className="max-w-3xl px-4 py-10 md:px-8">
      <h1 className="text-title">Составление</h1>

      {check && (
        <p className="mt-2 text-pencil">
          {check.stats.classes} классов, {check.stats.teachers} учителей, {check.stats.rooms} кабинетов,{" "}
          {check.stats.hours} уроков в неделю.
        </p>
      )}

      {blocked && (
        <Notice tone="no" title="Сначала исправьте данные" className="mt-6">
          <ul className="list-disc space-y-1 pl-5">
            {check!.problems.slice(0, 12).map((p) => <li key={p}>{p}</li>)}
          </ul>
          {check!.problems.length > 12 && (
            <p className="mt-2 text-pencil">и ещё {check!.problems.length - 12}</p>
          )}
        </Notice>
      )}

      {check && check.warnings.length > 0 && (
        <Notice tone="worse" className="mt-6">
          <ul className="list-disc space-y-1 pl-5">
            {check.warnings.map((w) => <li key={w}>{w}</li>)}
          </ul>
        </Notice>
      )}

      <fieldset disabled={running} className="mt-8 grid gap-8 md:grid-cols-2">
        <Choice name="preset" legend="Чьё удобство важнее" value={preset}
                options={presets.map((p) => ({ value: p.name, label: p.name, about: p.about }))}
                onChange={setPreset} />
        <div>
          <Segmented legend="Сколько искать" value={budget} options={BUDGETS} onChange={setBudget} />
          <p className="mt-3 max-w-prose text-small text-pencil">
            Законная сетка появляется за секунды. Остальное время система убирает окна
            и выравнивает дни — чем дольше, тем удобнее.
          </p>
        </div>
      </fieldset>

      <div className="mt-8">
        {!running ? (
          <Button variant="primary" size="lg" disabled={blocked || !check} onClick={start}>
            Составить расписание
          </Button>
        ) : (
          <Button size="lg" onClick={() => job && api.stop(job)}>
            Остановить и взять лучшее
          </Button>
        )}
      </div>

      {running && (
        <Panel className="mt-8 p-5">
          <div aria-live="polite">
            <div className="h-1 overflow-hidden rounded-full bg-rule">
              <div className="h-full bg-pen transition-[width] duration-500"
                   style={{ width: `${Math.min(100, (elapsed / budget) * 100)}%` }} />
            </div>
            <p className="mt-3 text-small text-pencil">
              {Math.round(elapsed)} с из {budget}.{" "}
              {progress?.solutions ? `Найдено вариантов: ${progress.solutions}.` : "Ищу первую законную сетку…"}
            </p>
          </div>
          {progress && Object.keys(progress.metrics).length > 0 && (
            <dl className="mt-5 grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-3">
              {Object.entries(progress.metrics).map(([label, value]) => (
                <Stat key={label} label={label} value={value} was={first?.metrics[label]} />
              ))}
            </dl>
          )}
        </Panel>
      )}

      {done?.type === "problems" && (
        <Notice tone="no" title="Составить не получилось — мешают данные" className="mt-8">
          <ul className="list-disc pl-5">{done.problems?.map((p) => <li key={p}>{p}</li>)}</ul>
        </Notice>
      )}
      {done?.type === "error" && (
        <Notice tone="no" title="Составление остановилось с ошибкой" className="mt-8">
          <pre className="whitespace-pre-wrap font-sans">{done.error}</pre>
        </Notice>
      )}
      {done?.type === "result" && !done.schedule_id && (
        <Notice tone="worse" title="Расписание с такими данными не находится" className="mt-8">
          Проверьте кабинеты и нагрузку: часов не может быть больше, чем уроков в сетке.
        </Notice>
      )}
    </div>
  );
}
