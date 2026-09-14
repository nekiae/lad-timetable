import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { api, type Progress, type SearchSetup, type SolveDone } from "../api";
import { Button, ButtonLink, Choice, Notice, Segmented } from "../ui";
import { SearchView, type Grids } from "./SearchView";

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
  // Для живого показа поиска: весь ход (без сеток — они тяжёлые), справочник
  // уроков и две последние сетки, чтобы подсветить, что переставлено.
  const [timeline, setTimeline] = useState<Progress[]>([]);
  const [setup, setSetup] = useState<SearchSetup>();
  const [grids, setGrids] = useState<Grids>();
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
    setTimeline([]);
    setSetup(undefined);
    setGrids(undefined);
    const { job_id } = await api.solve(id, { budget, preset });
    setJob(job_id);
    unwatch.current = api.watch(
      job_id,
      (p) => {
        setProgress(p);
        if (Object.keys(p.metrics).length) setFirst((f) => f ?? p);
        setTimeline((t) => [...t, { ...p, grid: null }]);
        if (p.grid) setGrids((g) => ({ current: p.grid!, previous: g?.current ?? null }));
      },
      (d) => {
        setDone(d);
        if (d.type === "result" && d.schedule_id) navigate(`/s/${id}/schedule`);
      },
      setSetup,
    );
  }

  const running = Boolean(job && !done);
  // Пустая школа — не ошибка данных, а незаполненные данные: кнопка
  // «Составить» здесь бессмысленна, главное действие — пойти их вносить.
  const empty = Boolean(check && check.stats.hours === 0);
  const blocked = Boolean(check?.problems.length) || empty;

  return (
    <div className="max-w-4xl px-4 py-10 md:px-8">
      <h1 className="text-title">Составление</h1>

      {check && (
        <p className="mt-2 text-pencil">
          {check.stats.classes} классов, {check.stats.teachers} учителей, {check.stats.rooms} кабинетов,{" "}
          {check.stats.hours} уроков в неделю.
        </p>
      )}

      {empty && (
        <Notice tone="info" title="Данных школы пока нет" className="mt-6">
          <p>Составлять не из чего: нужны классы, учителя и нагрузка.</p>
          <div className="mt-3"><ButtonLink to={`/s/${id}/data`} variant="primary">Внести данные школы</ButtonLink></div>
        </Notice>
      )}

      {blocked && !empty && (
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

      {/* Пока идёт поиск, настройки сворачиваются в строку: иначе живой показ
          уходит ниже первого экрана, а смотреть надо именно на него. */}
      {running ? (
        <p className="mt-6 text-pencil">
          {preset}, {BUDGETS.find((b) => b.value === budget)?.label ?? `${budget} с`}.
        </p>
      ) : (
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
      )}

      <div className={running ? "mt-4" : "mt-8"}>
        {empty ? null : !running ? (
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
        <div className="mt-8">
          <SearchView budget={budget} elapsed={elapsed} progress={progress} first={first}
                      timeline={timeline} setup={setup} grids={grids} />
        </div>
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
