import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import { api, type Change, type Comparison, type ComparisonSide, type Directory, type LessonDTO, type Progress,
         type SolveDone } from "../api";
import { alias, masker, useHideNames } from "../hideNames";
import { Button, ButtonLink, EmptyState, Notice, Panel, Segmented, cx, inputClass } from "../ui";
import { short } from "./SchedulePage";

// На этом экране завуч выбирает изменение сам. Пожелание из «Поправить»
// (kind: "aim") сюда не попадает — оно приходит готовым в адресе страницы.
type Kind = Exclude<Change["kind"], "aim">;
type Running = {
  label: string;
  budget: number;
  started: number;
  jobs: { control: string; variant: string };
  progress: { control?: Progress; variant?: Progress };
  done: { control?: SolveDone; variant?: SolveDone };
  stopped?: boolean;
};

// Поле ввода из кирпичей растянуто на всю ширину — для выпадающих списков
// в строку это лишнее: ширина по содержимому.
const selectClass = inputClass.replace("w-full", "w-auto max-w-full");

const DAYS = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница"];
const MODES = [
  { value: "keep" as const, label: "Беречь текущее расписание" },
  { value: "fresh" as const, label: "Составить с нуля" },
];

// «Что если»: завуч пробует одно изменение, не трогая расписание школы.
// Система составляет ДВА варианта одновременно и одинаково — без изменения
// и с ним, — поэтому разница между ними от изменения, а не от того, что один
// поиск шёл дольше или ему повезло (CLAUDE.md §8.3, server/whatif.py).
export function WhatIfPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  // Круг правки: сколько уроков системе разрешено двигать. Закреплённое
  // считает она сама — руками восемьсот уроков не закрепишь.
  const [ring, setRing] = useState<{ name: string; movable: number; total: number }>();
  const [dir, setDir] = useState<Directory | null>();
  const [settings, setSettings] = useState<Record<string, unknown>>({});
  const [methodDays, setMethodDays] = useState<Record<string, number>>({});
  const [presets, setPresets] = useState<string[]>([]);
  const [rules, setRules] = useState<{ key: string; title: string; default: string }[]>([]);
  const [seats, setSeats] = useState<number | null>(null);

  const [kind, setKind] = useState<Kind>("teacher_day_off");
  const [teacher, setTeacher] = useState("");
  const [day, setDay] = useState(3);
  const [preset, setPreset] = useState("");
  const [rule, setRule] = useState("");
  const [ruleValue, setRuleValue] = useState("soft");
  const [mode, setMode] = useState<"keep" | "fresh">("keep");

  const [running, setRunning] = useState<Running | null>(null);
  const [now, setNow] = useState(Date.now());
  const [error, setError] = useState<string | null>(null);
  // Изменение, при котором расписание не сложится в принципе, — с причинами.
  const [blocked, setBlocked] = useState<{ label: string; reasons: string[] } | null>(null);
  const [result, setResult] = useState<Comparison | null>(null);
  const [applying, setApplying] = useState(false);
  const unwatch = useRef<(() => void)[]>([]);

  useEffect(() => {
    api.latest(id).then((s) => setDir(s.directory)).catch(() => setDir(null));
    api.school(id).then((s) => {
      setSettings(s.doc.settings);
      setMethodDays(Object.fromEntries((s.doc.tables.teachers ?? []).map((t) =>
        [String(t["ФИО"] ?? "").trim(), Number(t["методический день"]) || 0])));
    });
    api.rules().then((r) => {
      setPresets(r.presets.map((p) => p.name));
      setRules(r.rules);
    });
    api.check(id).then((c) => setSeats(c.pe.gyms ? c.pe.seats : null)).catch(() => undefined);
    return () => unwatch.current.forEach((stop) => stop());
  }, [id]);

  // Правка пришла с готового расписания («Поправить»): изменение уже выбрано,
  // круг тоже. Считаем сразу, не заставляя завуча собирать его заново.
  const fromFix = params.get("aim");
  const fixRing = Number(params.get("ring") ?? 0);
  const fixStarted = useRef(false);
  useEffect(() => {
    if (!fromFix || fixStarted.current) return;
    fixStarted.current = true;
    try {
      start(JSON.parse(decodeURIComponent(fromFix)) as Change, fixRing);
    } catch {
      setError("Не понял, что именно поправить");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fromFix]);

  const control = params.get("control");
  const variant = params.get("variant");
  useEffect(() => {
    if (!control || !variant) {
      setResult(null);
      return;
    }
    api.whatIfCompare(id, control, variant).then(setResult).catch((e) => setError(String(e.message ?? e)));
  }, [id, control, variant]);

  useEffect(() => {
    if (!running) return;
    const timer = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(timer);
  }, [running]);

  const currentPreset = typeof settings.preset === "string" ? settings.preset : "Поровну";
  const strict = (settings.rules as Record<string, string>) ?? {};
  const hardRules = rules.filter((r) => (strict[r.key] ?? r.default) === "hard");
  const teachers = dir ? Object.values(dir.teachers).sort((a, b) => a.localeCompare(b, "ru")) : [];
  // Список учителей и причины отказа приходят с фамилиями — при общем
  // обезличивании их надо закрыть и здесь (§8.4). Значение в списке остаётся
  // настоящим: его отправляем солверу.
  const [hideNames] = useHideNames();
  const mask = masker(hideNames, dir?.teachers ?? {});

  useEffect(() => {
    if (!teacher && teachers.length) setTeacher(teachers[0]);
    if (!preset && presets.length) setPreset(presets.find((p) => p !== currentPreset) ?? presets[0]);
    if (!rule && hardRules.length) setRule(hardRules[0].key);
  }, [teachers, presets, hardRules, teacher, preset, rule, currentPreset]);

  if (dir === undefined) return <p className="px-4 py-10 text-pencil md:px-8">Загружаю…</p>;
  if (dir === null)
    return (
      <EmptyState text="Сначала составьте расписание: сравнивать изменение не с чем."
                  action={<ButtonLink to={`/s/${id}`} variant="primary">Перейти к составлению</ButtonLink>} />
    );

  // Способ расчёта по умолчанию зависит от вопроса. «Учитель не может в среду» —
  // вопрос «что придётся переставить», значит беречь текущее. Зал, режим и
  // нормы — вопрос «какое расписание вообще возможно»: при бережном расчёте
  // штраф за перестановку держит сетку на месте, и эффект не виден (замер
  // 15.09.2026: зал +1 класс от текущего расписания — переставлен 1 урок).
  function pickKind(next: Kind) {
    setKind(next);
    setMode(next === "teacher_day_off" ? "keep" : "fresh");
  }

  function change(): Change {
    if (kind === "teacher_day_off") return { kind, teacher, day };
    if (kind === "gym_plus") return { kind };
    if (kind === "preset") return { kind, preset };
    return { kind: "rule", rule, value: ruleValue };
  }

  async function start(ready?: Change, ring = 2) {
    setError(null);
    setBlocked(null);
    setParams({});
    try {
      // `ready` приходит из «Поправить» на готовой сетке: изменение уже
      // выбрано, спрашивать нечего — сразу считаем его цену.
      const started = await api.whatIf(id, ready ?? change(), mode, ring);
      setRing({ name: started.ring_name, movable: started.movable, total: started.total });
      if (started.blocked) {
        setBlocked({ label: started.label, reasons: started.blocked });
        return;
      }
      const run: Running = { label: started.label, budget: started.budget, started: Date.now(),
                             jobs: { control: started.control, variant: started.variant }, progress: {}, done: {} };
      setRunning(run);
      const finished: Running["done"] = {};
      unwatch.current = (["control", "variant"] as const).map((role) =>
        api.watch(run.jobs[role],
          (p) => setRunning((r) => (r ? { ...r, progress: { ...r.progress, [role]: p } } : r)),
          (d) => {
            finished[role] = d;
            setRunning((r) => (r ? { ...r, done: { ...r.done, [role]: d } } : r));
            if (!finished.control || !finished.variant) return;
            setRunning(null);
            const failed = (["control", "variant"] as const).find((x) => !finished[x]!.schedule_id);
            if (!failed) {
              setParams({ control: finished.control.schedule_id!, variant: finished.variant.schedule_id! });
            } else {
              const d = finished[failed]!;
              setError(d.type === "problems" ? `В данных школы ошибки: ${d.problems?.[0] ?? ""}`
                : d.type === "error" ? "Расчёт остановился с ошибкой."
                  : failed === "variant"
                    ? `С этим изменением расписание не складывается: «${run.label}». Это тоже ответ — так делать нельзя.`
                    : "Остановлено раньше, чем нашлось расписание.");
            }
          }));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  function stop() {
    if (!running) return;
    setRunning({ ...running, stopped: true });
    api.stop(running.jobs.control);
    api.stop(running.jobs.variant);
  }

  async function accept() {
    if (!result || !control || !variant) return;
    setApplying(true);
    try {
      await api.whatIfApply(id, control, variant);
      navigate(`/s/${id}/schedule`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setApplying(false);
    }
  }

  const sameDay = kind === "teacher_day_off" && methodDays[teacher] === day;

  return (
    <div className="max-w-5xl px-4 py-10 md:px-8">
      <h1 className="text-title">Что если</h1>
      <p className="mt-2 max-w-prose text-pencil">
        Попробуйте изменение, не трогая расписание школы. Система составит два варианта одинаково — без изменения
        и с ним — и покажет, что станет лучше и что хуже.
      </p>

      {!running && !result && (
        <>
          <fieldset className="mt-8">
            <legend className="mb-2 text-heading">Что изменить</legend>
            <div className="space-y-2">
              <Option on={kind === "teacher_day_off"} onPick={() => pickKind("teacher_day_off")}
                      title="Учитель не может в какой-то день"
                      about="Курсы, работа в другой школе, учёба по графику.">
                <div className="mt-3 flex flex-wrap gap-3">
                  <select className={selectClass} value={teacher} aria-label="Учитель"
                          onChange={(e) => setTeacher(e.target.value)}>
                    {teachers.map((name) => <option key={name} value={name}>{mask(name)}</option>)}
                  </select>
                  <select className={selectClass} value={day} aria-label="День"
                          onChange={(e) => setDay(Number(e.target.value))}>
                    {DAYS.slice(0, dir.days.length).map((name, n) => <option key={name} value={n + 1}>{name}</option>)}
                  </select>
                </div>
                {sameDay && (
                  <p className="mt-2 text-small text-worse">Это и так методический день учителя — варианты выйдут одинаковыми.</p>
                )}
              </Option>
              {seats !== null && (
                <Option on={kind === "gym_plus"} onPick={() => pickKind("gym_plus")}
                        title="В спортзале занимается на один класс больше"
                        about={`Сейчас в залах одновременно ${seats}. Спортзалы — самое тесное место школы.`} />
              )}
              <Option on={kind === "preset"} onPick={() => pickKind("preset")}
                      title="Другой режим «Чьё удобство важнее»"
                      about={`Сейчас — «${currentPreset}».`}>
                <select className={cx(selectClass, "mt-3")} value={preset} aria-label="Режим"
                        onChange={(e) => setPreset(e.target.value)}>
                  {presets.filter((p) => p !== currentPreset).map((p) => <option key={p}>{p}</option>)}
                </select>
              </Option>
              {hardRules.length > 0 && (
                <Option on={kind === "rule"} onPick={() => pickKind("rule")}
                        title="Применять норму мягче"
                        about="Сколько удобства даёт отступление от нормы — и стоит ли оно того.">
                  <div className="mt-3 flex flex-wrap gap-3">
                    <select className={selectClass} value={rule} aria-label="Норма"
                            onChange={(e) => setRule(e.target.value)}>
                      {hardRules.map((r) => <option key={r.key} value={r.key}>{r.title}</option>)}
                    </select>
                    <select className={selectClass} value={ruleValue} aria-label="Строгость"
                            onChange={(e) => setRuleValue(e.target.value)}>
                      <option value="soft">Мягко</option>
                      <option value="off">Не учитывать</option>
                    </select>
                  </div>
                </Option>
              )}
            </div>
          </fieldset>

          <div className="mt-8">
            <Segmented legend="Как считать" value={mode} options={MODES} onChange={setMode} />
            <p className="mt-3 max-w-prose text-small text-pencil">
              {mode === "keep"
                ? "Оба варианта стартуют с текущего расписания и двигают как можно меньше уроков. Минута. Так видно, что придётся переставить."
                : "Оба варианта составляются заново. Две минуты. Так видно, какое расписание вообще возможно с изменением."}
            </p>
          </div>

          <Button variant="primary" size="lg" className="mt-8"
                  disabled={(kind === "teacher_day_off" && !teacher) || (kind === "rule" && !rule)}
                  onClick={() => start()}>
            Посчитать два варианта
          </Button>
        </>
      )}

      {blocked && !running && !result && (
        <Notice tone="no" className="mt-6" title="Так расписание не сложится">
          <p>{mask(blocked.label)}. Причины:</p>
          <ul className="mt-1 list-disc space-y-1 pl-5">
            {blocked.reasons.map((r) => <li key={r}>{mask(r)}</li>)}
          </ul>
          <p className="mt-2">Выберите другой день или сначала поменяйте нагрузку учителя.</p>
        </Notice>
      )}
      {error && <Notice tone="no" className="mt-6" title="Не получилось">{error}</Notice>}

      {running && <RunningView running={running} now={now} onStop={stop} />}

      {result && (
        <ResultView result={result} dir={dir} applying={applying} onAccept={accept}
                    onAgain={() => { setParams({}); setError(null); }} />
      )}
    </div>
  );
}

function Option({ on, onPick, title, about, children }: {
  on: boolean; onPick: () => void; title: string; about: string; children?: React.ReactNode;
}) {
  return (
    <div className={cx("rounded border px-3 py-2 transition-colors duration-150",
                       on ? "border-pen bg-pen-soft" : "border-rule bg-sheet hover:border-pencil")}>
      <label className="block cursor-pointer has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-pen">
        <input type="radio" name="change" className="sr-only" checked={on} onChange={onPick} />
        <span className="font-medium">{title}</span>
        <span className="mt-0.5 block text-small text-pencil">{about}</span>
      </label>
      {on && children}
    </div>
  );
}

function RunningView({ running, now, onStop }: { running: Running; now: number; onStop: () => void }) {
  const elapsed = Math.max(0, (now - running.started) / 1000);
  return (
    <section className="mt-8">
      <p className="text-heading">{running.label}</p>
      <p className="mt-1 text-pencil">
        Считаю два варианта одновременно: {Math.round(elapsed)} с из {running.budget}.
      </p>
      <div className="mt-3 h-1 max-w-xl overflow-hidden rounded-full bg-rule">
        <div className="h-full bg-pen transition-[width] duration-500"
             style={{ width: `${Math.min(100, (elapsed / running.budget) * 100)}%` }} />
      </div>
      <div className="mt-5 grid gap-4 sm:grid-cols-2">
        {(["control", "variant"] as const).map((role) => {
          const p = running.progress[role];
          const found = p && Object.keys(p.metrics).length > 0;
          return (
            <Panel key={role} as="div" className="text-small">
              <p className="font-semibold">{role === "control" ? "Без изменения" : "С изменением"}</p>
              <p className="mt-1 text-pencil">
                {running.done[role] ? (running.done[role]!.schedule_id ? "Готово." : "Расписание не нашлось.") : !found ? "Ищу законную сетку…"
                  : p!.phase === "polish" ? "Нормы закрыты, улучшаю удобство." : "Закрываю нормы."}
              </p>
              {found && (
                <dl className="mt-2 grid grid-cols-2 gap-2">
                  {["Нарушений норм", "Окна у учителей"].filter((k) => k in p!.metrics).map((k) => (
                    <div key={k}>
                      <dt className="text-pencil">{k}</dt>
                      <dd className="text-heading">{p!.metrics[k]}</dd>
                    </div>
                  ))}
                </dl>
              )}
            </Panel>
          );
        })}
      </div>
      <Button className="mt-5" disabled={running.stopped} onClick={onStop}>
        {running.stopped ? "Останавливаю…" : "Остановить и сравнить найденное"}
      </Button>
    </section>
  );
}

type Metric = keyof ComparisonSide["metrics"];

// Меньше — лучше у всех строк. `exact` — нормы и конфликты: там любая разница
// настоящая. У остальных разница в пределах 10% — шум поиска, а не эффект
// изменения: тот же расчёт с другим сидом даёт окна 55–63 (замер 15.09.2026).
const ROWS: { key: Metric; label: string; exact?: boolean }[] = [
  { key: "norms", label: "Нарушений санитарных норм", exact: true },
  { key: "conflicts", label: "Конфликтов в сетке", exact: true },
  { key: "teacher_gaps", label: "Окна у учителей за неделю" },
  { key: "teacher_single_days", label: "Выходов в школу ради одного урока" },
  { key: "teacher_days", label: "Рабочих дней у учителей" },
  { key: "classes_spread_3plus", label: "Классов, где дни отличаются на 3+ урока" },
  { key: "adjacent_two", label: "Предмет на 2 часа в соседние дни" },
  { key: "three_in_row", label: "Предмет на 3 часа три дня подряд" },
  { key: "monday_heavy", label: "Классов с самым трудным днём в понедельник" },
];

function delta(a: number, b: number, exact?: boolean) {
  const d = b - a;
  const noise = exact ? 0 : Math.max(1, Math.round(Math.max(a, b) * 0.1));
  return { d, level: Math.abs(d) <= noise ? "same" : d < 0 ? "better" : "worse" } as const;
}

function ResultView({ result, dir, applying, onAccept, onAgain }: {
  result: Comparison; dir: Directory; applying: boolean; onAccept: () => void; onAgain: () => void;
}) {
  const a = result.control.metrics, b = result.variant.metrics;
  const rows = ROWS.map((row) => ({ ...row, a: a[row.key], b: b[row.key], ...delta(a[row.key], b[row.key], row.exact) }));
  const better = rows.filter((r) => r.level === "better");
  const worse = rows.filter((r) => r.level === "worse");
  const lower = (s: string) => s.charAt(0).toLowerCase() + s.slice(1);

  return (
    <section className="mt-8">
      <p className="text-heading">{result.label}</p>
      <p className="mt-1 max-w-prose text-small text-pencil">
        Оба варианта составлены одинаково: {result.mode === "keep" ? "от текущего расписания" : "с нуля"}, по{" "}
        {result.budget} с. Отличаются только этим изменением.
      </p>

      <div className="mt-5 max-w-prose space-y-2">
        {better.length === 0 && worse.length === 0 && (
          <p>Заметной разницы нет: изменение расписанию не мешает и не помогает.</p>
        )}
        {better.length > 0 && (
          <p><span className="font-semibold text-ok">Лучше:</span> {better.map((r) => `${lower(r.label)} ${r.a} → ${r.b}`).join("; ")}.</p>
        )}
        {worse.length > 0 && (
          <p><span className="font-semibold text-worse">Хуже:</span> {worse.map((r) => `${lower(r.label)} ${r.a} → ${r.b}`).join("; ")}.</p>
        )}
        {result.mode === "keep" && (
          <p className="text-pencil">
            Переставить придётся уроков: {b.moved} (без изменения система сама переставила бы {a.moved}).
            {result.ring < 2 && ` Ворошили ${result.ring_name}: остальное осталось на местах.`}
          </p>
        )}
      </div>

      <div className="mt-6 overflow-x-auto rounded-lg border border-rule bg-sheet">
        <table className="w-full min-w-[520px] border-collapse text-left">
          <thead>
            <tr className="border-b border-rule text-small text-pencil">
              <th className="px-4 py-2 font-medium">Показатель</th>
              <th className="px-4 py-2 text-right font-medium">Без изменения</th>
              <th className="px-4 py-2 text-right font-medium">С изменением</th>
              <th className="px-4 py-2 text-right font-medium">Разница</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.key} className="border-b border-rule last:border-0">
                <td className="px-4 py-2">{r.label}</td>
                <td className="px-4 py-2 text-right">{r.a}</td>
                <td className="px-4 py-2 text-right font-semibold">{r.b}</td>
                <td className={cx("px-4 py-2 text-right",
                                  r.level === "better" ? "text-ok" : r.level === "worse" ? "text-worse" : "text-pencil")}>
                  {r.d === 0 ? "—" : r.level === "same" ? `≈ ${r.d > 0 ? "+" : "−"}${Math.abs(r.d)}` : `${r.d > 0 ? "+" : "−"}${Math.abs(r.d)}`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-small text-pencil">≈ — разница в пределах 10%: столько даёт сам поиск при повторном расчёте.</p>

      <WeekCompare result={result} dir={dir} />

      {result.stale && (
        <Notice tone="worse" className="mt-6">
          Данные школы изменились после расчёта. Принять этот вариант уже нельзя — посчитайте заново.
        </Notice>
      )}
      {/* Нормы дороже любого удобства: вариант, где их нарушено больше, принимать
          нельзя. Это не совет, а запрет — за нормы отвечает завуч, и подписывать
          ему придётся то, что мы показали. */}
      {b.norms > a.norms && (
        <Notice tone="no" title="Нарушений санитарных норм стало больше" className="mt-6">
          Было {a.norms}, стало {b.norms}. Принять такой вариант нельзя.
          {result.ring < 2 && " Попробуйте разрешить трогать больше уроков — сейчас правка была точечной."}
        </Notice>
      )}
      <div className="mt-6 flex flex-wrap items-center gap-3">
        <Button variant="primary"
                disabled={applying || result.stale || b.conflicts > 0 || b.norms > a.norms}
                onClick={onAccept}>
          {applying ? "Принимаю…" : "Принять изменение"}
        </Button>
        <Button onClick={onAgain}>Попробовать другое</Button>
      </div>
      <p className="mt-2 max-w-prose text-small text-pencil">
        «Принять» запишет изменение в данные школы, и расписание с ним станет текущим. Прежнее останется
        в истории версий.
      </p>
    </section>
  );
}

// Неделя одного класса или учителя в двух вариантах рядом. Клетки, где
// варианты расходятся, подсвечены — остальное совпадает.
function WeekCompare({ result, dir }: { result: Comparison; dir: Directory }) {
  const teacherId = result.change.kind === "teacher_day_off"
    ? Object.entries(dir.teachers).find(([, name]) => name === (result.change as { teacher: string }).teacher)?.[0]
    : undefined;

  const cells = (lessons: LessonDTO[], who: string) => {
    const map = new Map<string, string>();
    const [type, key] = who.split(":");
    for (const l of lessons) {
      const classes = dir.groups[l.group_id]?.class_ids ?? [];
      if (type === "c" ? !classes.includes(key) : l.teacher_id !== key) continue;
      const text = type === "c" ? short(dir.subjects[l.subject_id] ?? "")
        : `${short(dir.subjects[l.subject_id] ?? "")} ${classes.map((c) => dir.classes.find((x) => x.id === c)?.name ?? c).join(", ")}`;
      const at = `${l.day}-${l.period}`;
      const now = map.get(at);
      if (!now?.split(" / ").includes(text)) map.set(at, now ? `${now} / ${text}` : text);
    }
    return map;
  };

  // По умолчанию — учитель из изменения, иначе класс, где разница больше всего.
  const initial = useMemo(() => {
    if (teacherId) return `t:${teacherId}`;
    let best = dir.classes[0] ? `c:${dir.classes[0].id}` : "";
    let most = -1;
    for (const c of dir.classes) {
      const x = cells(result.control.lessons, `c:${c.id}`), y = cells(result.variant.lessons, `c:${c.id}`);
      const keys = new Set([...x.keys(), ...y.keys()]);
      const diff = [...keys].filter((k) => x.get(k) !== y.get(k)).length;
      if (diff > most) [best, most] = [`c:${c.id}`, diff];
    }
    return best;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [result]);
  const [who, setWho] = useState(initial);
  useEffect(() => setWho(initial), [initial]);
  const [hideNames] = useHideNames();

  const left = cells(result.control.lessons, who), right = cells(result.variant.lessons, who);
  const teachers = Object.entries(dir.teachers).sort(([, x], [, y]) => x.localeCompare(y, "ru"));

  return (
    <div className="mt-8">
      <div className="flex flex-wrap items-center gap-3">
        <p className="text-heading">Неделя рядом</p>
        <select className={selectClass} value={who} aria-label="Чья неделя" onChange={(e) => setWho(e.target.value)}>
          <optgroup label="Классы">
            {dir.classes.map((c) => <option key={c.id} value={`c:${c.id}`}>{c.name}</option>)}
          </optgroup>
          <optgroup label="Учителя">
            {teachers.map(([tid]) => (
              <option key={tid} value={`t:${tid}`}>{alias(hideNames, dir.teachers, tid)}</option>
            ))}
          </optgroup>
        </select>
        <span className="text-small text-pencil">
          <span className="mr-1 inline-block h-3 w-3 rounded-sm border border-pen bg-pen-soft align-middle" /> отличается
        </span>
      </div>
      <div className="mt-3 grid gap-4 md:grid-cols-2">
        {[{ title: "Без изменения", map: left }, { title: "С изменением", map: right }].map((side) => (
          <div key={side.title} className="min-w-0">
            <p className="mb-1 text-small font-semibold">{side.title}</p>
            <div className="overflow-x-auto rounded-lg border border-rule bg-sheet">
              <table className="w-full table-fixed border-collapse font-narrow text-cell">
                <thead>
                  <tr className="text-small text-pencil">
                    <th className="w-7 border-b border-rule" />
                    {dir.days.map((d) => <th key={d.n} className="border-b border-l border-rule px-1 py-1 text-left font-medium">{d.name.slice(0, 2)}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {Array.from({ length: dir.periods }, (_, p) => p + 1).map((period) => (
                    <tr key={period}>
                      <th className="border-t border-rule text-center font-normal text-pencil">{period}</th>
                      {dir.days.map((d) => {
                        const key = `${d.n}-${period}`;
                        const differs = left.get(key) !== right.get(key);
                        return (
                          <td key={key} className={cx("h-9 border-l border-t border-rule px-1 align-top",
                                                      differs && "bg-pen-soft shadow-[inset_0_0_0_1px] shadow-pen")}>
                            <span className="line-clamp-2">{side.map.get(key) ?? ""}</span>
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
