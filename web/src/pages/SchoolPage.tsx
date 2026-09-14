import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api, type Doc, type Progress, type SearchSetup, type SolveDone } from "../api";
import { Button, ButtonLink, Choice, Notice, Segmented, cx } from "../ui";
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
  const [rules, setRules] = useState<{ key: string; title: string; source: string | null; default: string }[]>([]);
  const [preferences, setPreferences] = useState<{ key: string; group: string; title: string; about: string; default: number }[]>([]);
  // Предпочтения школы: уровень 0–3 по каждому и какой день короткий. Хранятся
  // в данных школы (settings.prefs), как и строгость норм.
  const [prefs, setPrefs] = useState<Record<string, number>>({});
  // Строгость норм, выбранная школой. Хранится в данных школы (settings.rules):
  // это вход составления, как нагрузка, и должен переживать перезагрузку.
  const [strict, setStrict] = useState<Record<string, string>>({});
  const [doc, setDoc] = useState<Doc>();
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
    api.rules().then((r) => {
      setPresets(r.presets);
      setRules(r.rules);
      setPreferences(r.preferences);
    });
    api.school(id).then((s) => {
      setDoc(s.doc);
      setStrict((s.doc.settings.rules as Record<string, string>) ?? {});
      setPrefs((s.doc.settings.prefs as Record<string, number>) ?? {});
    });
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
    const { job_id } = await api.solve(id, { budget, preset, rules: effective, prefs: effectivePrefs });
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
  const effective = Object.fromEntries(rules.map((r) => [r.key, strict[r.key] ?? r.default]));

  const effectivePrefs: Record<string, number> = {
    ...Object.fromEntries(preferences.map((p) => [p.key, prefs[p.key] ?? p.default])),
    light_day_of_week: prefs.light_day_of_week ?? 5,
  };

  function setPref(key: string, value: number) {
    const next = { ...prefs, [key]: value };
    setPrefs(next);
    if (!doc) return;
    const saved = { ...doc, settings: { ...doc.settings, prefs: next } };
    setDoc(saved);
    api.saveSchool(id, saved);
  }

  function setRule(key: string, value: string) {
    const next = { ...strict, [key]: value };
    setStrict(next);
    if (!doc) return;
    const saved = { ...doc, settings: { ...doc.settings, rules: next } };
    setDoc(saved);
    api.saveSchool(id, saved).then(() => api.check(id).then(setCheck));
  }
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

      {!running && check && !empty && check.pe.hours > 0 && check.pe.seats > 0 && (
        <GymCard id={id} pe={check.pe} consecutive={effective.pe_two_days !== "hard"} />
      )}

      {!running && preferences.length > 0 && !empty && (
        <details open className="mt-8 rounded-lg border border-rule bg-sheet p-4">
          <summary className="cursor-pointer text-heading">
            Предпочтения школы
            {preferences.some((p) => (prefs[p.key] ?? p.default) !== p.default) && (
              <span className="ml-2 text-small font-normal text-worse">изменено школой</span>
            )}
          </summary>
          <p className="mt-2 max-w-prose text-small text-pencil">
            Что важнее, когда всё сразу не выходит. «Важно» — как в выбранном режиме выше. Санитарные нормы
            всё равно закрываются первыми, предпочтения работают после них.
          </p>
          {[...new Set(preferences.map((p) => p.group))].map((group) => (
            <div key={group} className="mt-5">
              <p className="font-semibold">{group}</p>
              <ul className="divide-y divide-rule">
                {preferences.filter((p) => p.group === group).map((pref) => {
                  const level = prefs[pref.key] ?? pref.default;
                  return (
                    <li key={pref.key} className="flex flex-wrap items-center justify-between gap-3 py-3">
                      <span className="min-w-0 max-w-prose">
                        <span className="block font-medium">{pref.title}</span>
                        <span className="block text-small text-pencil">{pref.about}</span>
                        {pref.key === "light_day" && level > 0 && (
                          <label className="mt-2 flex items-center gap-2 text-small">
                            Какой день:
                            <select className="rounded border border-rule bg-sheet px-2 py-1"
                                    value={prefs.light_day_of_week ?? 5}
                                    onChange={(e) => setPref("light_day_of_week", Number(e.target.value))}>
                              {["Понедельник", "Вторник", "Среда", "Четверг", "Пятница"].map((name, n) => (
                                <option key={name} value={n + 1}>{name}</option>
                              ))}
                            </select>
                          </label>
                        )}
                      </span>
                      <span className="inline-flex shrink-0 rounded border border-rule bg-sheet p-0.5" role="group"
                            aria-label={pref.title}>
                        {LEVELS.map(([value, label]) => (
                          <button key={value} type="button" aria-pressed={level === value}
                                  onClick={() => setPref(pref.key, value)}
                                  className={cx("rounded-[4px] px-3 py-1 text-small font-medium transition-colors duration-150",
                                                level === value ? "bg-pen text-white" : "text-ink hover:bg-paper")}>
                            {label}
                          </button>
                        ))}
                      </span>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </details>
      )}

      {!running && rules.length > 0 && !empty && (
        <details className="mt-8 rounded-lg border border-rule bg-sheet p-4">
          <summary className="cursor-pointer text-heading">
            Как строго применять нормы
            {rules.some((r) => (strict[r.key] ?? r.default) !== r.default) && (
              <span className="ml-2 text-small font-normal text-worse">изменено школой</span>
            )}
          </summary>
          <p className="mt-2 max-w-prose text-small text-pencil">
            «Жёстко» — так не поставится никогда. «Мягко» — поставится, только если иначе расписание не
            складывается, и каждый такой случай будет в отчёте. «Не учитывать» — норма выключена.
          </p>
          <ul className="mt-4 divide-y divide-rule">
            {rules.map((rule) => (
              <li key={rule.key} className="flex flex-wrap items-center justify-between gap-3 py-3">
                <span className="min-w-0">
                  <span className="block font-medium">{rule.title}</span>
                  {rule.source && <span className="block text-small text-pencil">{rule.source}</span>}
                </span>
                <span className="inline-flex shrink-0 rounded border border-rule bg-sheet p-0.5" role="group"
                      aria-label={rule.title}>
                  {STRICTNESS.map(([value, label]) => {
                    const on = (strict[rule.key] ?? rule.default) === value;
                    return (
                      <button key={value} type="button" aria-pressed={on} onClick={() => setRule(rule.key, value)}
                              className={cx("rounded-[4px] px-3 py-1 text-small font-medium transition-colors duration-150",
                                            on ? "bg-pen text-white" : "text-ink hover:bg-paper")}>
                        {label}
                      </button>
                    );
                  })}
                </span>
              </li>
            ))}
          </ul>
        </details>
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

const STRICTNESS: [string, string][] = [["hard", "Жёстко"], ["soft", "Мягко"], ["off", "Не учитывать"]];
const LEVELS: [number, string][] = [[0, "Не важно"], [1, "Немного"], [2, "Важно"], [3, "Очень"]];

// «1 урок», «3 урока», «72 урока», «5 уроков».
const plural = (n: number, one: string, few: string, many: string) => {
  const d = n % 10, h = n % 100;
  return d === 1 && h !== 11 ? one : d >= 2 && d <= 4 && (h < 12 || h > 14) ? few : many;
};

// Спортзалы — самое тесное место школы. Физкультуру нельзя два дня подряд
// (п. 94 ССЭТ), поэтому при трёх часах она встаёт только в пн/ср/пт — и зал
// бывает забит с первого урока до последнего. Тогда в эти дни классы учатся
// до 8-го урока, а во вторник и четверг — по 5: дни неровные не по вине
// алгоритма, а по арифметике залов (замер 14.09.2026). Здесь эта арифметика
// показана завучу вместе с рычагом, который по замеру работает.
//
// Кнопки «разрешить физкультуру два дня подряд» здесь НЕТ, и это не забыто.
// Замер 15.09.2026 (школа из примера, 120 с, 3 сида): норма «мягко» дала
// 3–4 нарушения вместо 0 и окна учителей 170–228 вместо 67 — солвер теряет
// подсказку «физкультура в пн/ср/пт», а каждый случай подряд всё равно считается
// нарушением. Зал на 3 класса вместо 2 дал 0 нарушений за 5–7 с вместо 21 с,
// окна 55–63 и вдвое меньше неровных дней. Переключатель нормы остался в «Как
// строго применять нормы» — но советовать его как выход нельзя.
function GymCard({ id, pe, consecutive }: {
  id: string;
  pe: { hours: number; gyms: number; seats: number; periods: number; days: number };
  consecutive: boolean;
}) {
  const days = consecutive ? pe.days : Math.ceil(pe.days / 2);
  const places = pe.seats * pe.periods * days;
  const load = places ? pe.hours / places : 1;
  const tight = load >= 0.9;
  return (
    <section className={cx("mt-8 rounded-lg border p-4", tight ? "border-worse/30 bg-worse-soft" : "border-rule bg-sheet")}>
      <p className="text-heading">{tight ? "Спортзалы заняты почти полностью" : "Спортзалы"}</p>
      <p className="mt-1 max-w-prose">
        Физкультура: {pe.hours} {plural(pe.hours, "урок", "урока", "уроков")} в неделю. В залах одновременно
        занимаются {pe.seats} {plural(pe.seats, "класс", "класса", "классов")}.{" "}
        {consecutive
          ? `Физкультура может стоять в любой из ${pe.days} ${plural(pe.days, "дня", "дней", "дней")} — это ${places} ${plural(places, "место", "места", "мест")}.`
          : `Без двух дней подряд она встаёт в ${days} ${plural(days, "день", "дня", "дней")} — это ${places} ${plural(places, "место", "места", "мест")}.`}{" "}
        Занято <span className="font-semibold">{Math.round(load * 100)}%</span>.
      </p>
      {tight && (
        <p className="mt-2 max-w-prose text-small">
          Поэтому дни у классов выходят неровными: в дни физкультуры залы заняты с первого урока до последнего,
          и часть классов учится до {pe.periods}-го урока, а в остальные дни — по 5. Если в зале можно заниматься
          ещё одному классу одновременно — укажите это: на примере школы на 24 класса это вдвое сократило
          неровные дни и окна учителей.
        </p>
      )}
      <div className="mt-3 flex flex-wrap gap-2">
        <Link to={`/s/${id}/data?step=rooms`}
              className="inline-flex items-center rounded border border-rule bg-sheet px-3 py-1.5 text-small font-medium hover:border-pencil">
          Изменить вместимость залов
        </Link>
      </div>
      {consecutive && (
        <p className="mt-2 text-small text-worse">
          Физкультура два дня подряд разрешена. На замере это сделало расписание хуже: больше окон у учителей
          и нарушения нормы. Лучше вернуть «Жёстко» и прибавить вместимость зала.
        </p>
      )}
    </section>
  );
}
