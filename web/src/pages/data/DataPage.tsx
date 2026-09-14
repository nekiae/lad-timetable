import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";

import { api, type Doc, type ImportReport, type InputState } from "../../api";
import { Button, ButtonLink, Notice, cx } from "../../ui";
import type { Row } from "../../ui/DataTable";
import { LoadStep } from "./LoadStep";
import { ClassesStep, RoomsStep, SchoolStep, SubjectsStep, TeachersStep } from "./steps";
import { WishesStep } from "./WishesStep";

export type StepProps = {
  schoolId: string;
  doc: Doc;
  input: InputState;
  /** Правка таблицы: сохраняется сама, с задержкой, пока человек печатает. */
  setRows: (table: string, rows: Row[]) => void;
  /** Правка настроек или пожеланий — так же, с задержкой. */
  update: (change: (doc: Doc) => Doc) => void;
  /** Действие на сервере (мастер, назначение): сначала досохраняет набранное. */
  run: <T extends { doc: Doc }>(action: () => Promise<T>) => Promise<T | undefined>;
};

// Порядок — как ведёт завуч, и он же порядок зависимостей: кабинеты сразу
// после классов, чтобы узнать «хватает ли комнат» до многочасового ввода
// нагрузки (так было и в Streamlit, проверено на завуче).
const ORDER = ["school", "classes", "rooms", "subjects", "teachers", "load", "wishes"] as const;
type StepKey = (typeof ORDER)[number];

const SCHOOL_STEP = {
  title: "Школа",
  why: "Рамка, в которую всё уложится: сколько уроков помещается в день и сколько дней в неделе идут уроки.",
};

// Ввод данных школы. Всё введённое сохраняется само — кнопки «Сохранить»
// нет, и потерять набранное, уйдя со страницы, нельзя.
export function DataPage() {
  const { id = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const [doc, setDoc] = useState<Doc>();
  const [input, setInput] = useState<InputState>();
  const [saving, setSaving] = useState<"idle" | "pending" | "saving" | "saved" | "error">("idle");
  const [error, setError] = useState<string>();
  const [report, setReport] = useState<ImportReport>();
  const fileInput = useRef<HTMLInputElement>(null);
  const latest = useRef<Doc>();
  const timer = useRef<number>();

  const fail = (e: unknown) => setError(e instanceof Error ? e.message : String(e));
  const refresh = useCallback(() => api.input(id).then(setInput).catch(fail), [id]);

  useEffect(() => {
    api.school(id).then((s) => {
      latest.current = s.doc;
      setDoc(s.doc);
    }).catch(fail);
    refresh();
  }, [id, refresh]);

  const persist = useCallback(async () => {
    if (!latest.current) return;
    setSaving("saving");
    try {
      await api.saveSchool(id, latest.current);
      setSaving("saved");
      refresh();
    } catch {
      setSaving("error");
    }
  }, [id, refresh]);

  // Уходя со страницы — досохранить то, что ещё ждёт задержки.
  useEffect(() => () => {
    if (timer.current !== undefined) {
      clearTimeout(timer.current);
      persist();
    }
  }, [persist]);

  const update = (change: (doc: Doc) => Doc) => {
    if (!latest.current) return;
    latest.current = change(latest.current);
    setDoc(latest.current);
    setSaving("pending");
    clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      timer.current = undefined;
      persist();
    }, 700);
  };

  const run = async <T extends { doc: Doc }>(action: () => Promise<T>) => {
    if (timer.current !== undefined) {
      clearTimeout(timer.current);
      timer.current = undefined;
      await persist();
    }
    setError(undefined);
    try {
      const result = await action();
      latest.current = result.doc;
      setDoc(result.doc);
      setSaving("saved");
      refresh();
      return result;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      return undefined;
    }
  };

  if (!doc || !input)
    return error ? (
      <div className="px-4 py-10 md:px-8">
        <Notice tone="no" title="Данные школы не открылись">
          {error}. Проверьте, что сервер запущен, и обновите страницу.
        </Notice>
      </div>
    ) : <p className="px-4 py-10 text-pencil md:px-8">Открываю данные школы…</p>;

  const steps = Object.fromEntries(input.steps.map((s) => [s.key, s]));
  const requested = params.get("step") as StepKey | null;
  const current: StepKey = requested && ORDER.includes(requested) ? requested : "school";
  const go = (key: StepKey) => {
    setParams({ step: key });
    window.scrollTo({ top: 0 });
  };
  const at = ORDER.indexOf(current);
  const next = ORDER[at + 1];
  const info = current === "school" ? SCHOOL_STEP : steps[current];
  const blocked = current === "school" ? [] : steps[current]?.blocked_by ?? [];

  const props: StepProps = {
    schoolId: id, doc, input, update, run,
    setRows: (table, rows) => update((d) => ({ ...d, tables: { ...d.tables, [table]: rows } })),
  };

  const savingText = {
    idle: "", pending: "Изменения сохранятся сами", saving: "Сохраняю…", saved: "Сохранено",
    error: "Не сохранилось. Проверьте, что сервер запущен, и повторите правку.",
  }[saving];

  return (
    <div className="px-4 py-8 md:px-8">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h1 className="text-title">Данные школы</h1>
        <div className="flex flex-wrap items-center gap-2">
          <p aria-live="polite" className={cx("mr-2 text-small", saving === "error" ? "text-no" : "text-pencil")}>
            {savingText}
          </p>
          <Button onClick={() => api.downloadData(id).catch(fail)}>Скачать в Excel</Button>
          {/* Загрузка заменяет только листы, которые есть в файле; прежние данные
              остаются в ревизиях школы. */}
          <Button onClick={() => fileInput.current?.click()}>Загрузить из Excel</Button>
          <input ref={fileInput} type="file" accept=".xlsx" className="hidden"
                 onChange={async (e) => {
                   const file = e.target.files?.[0];
                   e.target.value = "";
                   if (!file) return;
                   const result = await run(() => api.importData(id, file));
                   if (result) setReport(result.report);
                 }} />
        </div>
      </div>

      {report && (
        <Notice tone={Object.keys(report.unknown_columns).length || report.unknown_sheets.length ? "worse" : "ok"}
                className="mt-4"
                title={`Загружено из Excel: ${Object.entries(report.imported).map(([s, n]) => `${s} — ${n}`).join(", ")}`}>
          {report.unknown_sheets.length > 0 && <p>Листы не распознаны и пропущены: {report.unknown_sheets.join(", ")}.</p>}
          {Object.entries(report.unknown_columns).map(([sheet, cols]) => (
            <p key={sheet}>{sheet}: колонки не распознаны и пропущены — {cols.join(", ")}.</p>
          ))}
          {Object.entries(report.missing_columns).map(([sheet, cols]) => (
            <p key={sheet}>{sheet}: в файле не было колонок {cols.join(", ")} — они пустые.</p>
          ))}
          <button type="button" className="mt-1 text-pen underline-offset-4 hover:underline" onClick={() => setReport(undefined)}>
            Скрыть
          </button>
        </Notice>
      )}

      <div className="mt-6 flex gap-10 max-md:flex-col max-md:gap-6">
        <nav aria-label="Шаги ввода" className="w-56 shrink-0 max-md:w-full">
          <ol className="flex flex-col gap-1 max-md:flex-row max-md:flex-wrap">
            {ORDER.map((key, n) => {
              const step = steps[key];
              const note = key === "school"
                ? String(doc.settings.name || "без названия")
                : step?.done ? String(step.count) : step?.optional ? "по желанию" : "не заполнено";
              return (
                <li key={key}>
                  <button type="button" onClick={() => go(key)} aria-current={key === current ? "step" : undefined}
                          className={cx(
                            "flex w-full items-baseline gap-2 rounded px-3 py-2 text-left transition-colors duration-150",
                            key === current ? "bg-pen-soft text-pen" : "hover:bg-sheet")}>
                    <span className="w-4 shrink-0 text-small text-pencil">{n + 1}</span>
                    <span className="font-medium">{key === "school" ? SCHOOL_STEP.title : step?.title}</span>
                    <span className={cx("ml-auto truncate text-small max-md:hidden",
                                        step && !step.done && !step.optional ? "text-worse" : "text-pencil")}>
                      {note}
                    </span>
                  </button>
                </li>
              );
            })}
          </ol>
        </nav>

        <section className="min-w-0 max-w-5xl flex-1">
          <h2 className="text-heading">{info?.title}</h2>
          <p className="mt-1 max-w-prose text-pencil">{info?.why}</p>

          {blocked.length > 0 && (
            <Notice tone="info" className="mt-4" title={`Сначала нужно заполнить: ${blocked.join(", ")}`}>
              Здесь выбирают из уже введённого, поэтому без них шаг не заполнить.
            </Notice>
          )}
          {error && <Notice tone="no" className="mt-4" title="Действие не выполнилось">{error}</Notice>}

          <div className="mt-6">
            {current === "school" && <SchoolStep {...props} />}
            {current === "classes" && <ClassesStep {...props} />}
            {current === "rooms" && <RoomsStep {...props} />}
            {current === "subjects" && <SubjectsStep {...props} />}
            {current === "teachers" && <TeachersStep {...props} />}
            {current === "load" && <LoadStep {...props} />}
            {current === "wishes" && <WishesStep {...props} />}
          </div>

          <div className="mt-10 border-t border-rule pt-6">
            {next ? (
              <Button onClick={() => go(next)}>
                Дальше: {next === "school" ? SCHOOL_STEP.title : steps[next]?.title}
              </Button>
            ) : (
              <ButtonLink to={`/s/${id}`} variant="primary">Перейти к составлению</ButtonLink>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
