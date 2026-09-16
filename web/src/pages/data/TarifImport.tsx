import { useEffect, useRef, useState } from "react";

import { api, type Doc, type TarifBody, type TarifField, type TarifInspect, type TarifPreview,
         type TarifSettings } from "../../api";
import { Button, Notice, Panel, Segmented, cx, inputClass } from "../../ui";

const FIELDS: { key: TarifField; label: string; long: boolean; wide: boolean }[] = [
  { key: "teacher", label: "Учитель (ФИО)", long: true, wide: true },
  { key: "subject", label: "Предмет", long: true, wide: true },
  { key: "class", label: "Класс", long: true, wide: false },
  { key: "hours", label: "Часов в неделю", long: true, wide: false },
  { key: "subgroup", label: "Подгруппа", long: true, wide: false },
];
const LAYOUTS = [
  { value: "wide" as const, label: "Учитель × классы" },
  { value: "long" as const, label: "Строка на урок" },
];
const MODES = [
  { value: "replace" as const, label: "Заменить нагрузку" },
  { value: "add" as const, label: "Добавить к нагрузке" },
];
// Заголовок колонки — класс: «5А», «5 «А»», «5-а».
const CLASS_HEADER = /^\s*(\d{1,2})\s*[-–—\s"«»“”„']*\s*[А-ЯЁа-яёA-Za-z]\s*["»”']*\s*$/;
const selectClass = inputClass.replace("w-full", "w-full sm:w-auto");

function letter(index: number) {
  let name = "";
  for (let n = index + 1; n > 0; n = Math.floor((n - 1) / 26)) name = String.fromCharCode(65 + ((n - 1) % 26)) + name;
  return name;
}

async function toBase64(file: File) {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(binary);
}

// Импорт своей таблицы нагрузки: завуч не перепечатывает тарификацию под наш
// шаблон, а показывает, какая колонка что значит. Система угадывает сама
// (lad/tarif_import.py), человек поправляет, справа сразу видно, что получится.
export function TarifImport({ id, run, onClose, onDone }: {
  id: string;
  run: <T extends { doc: Doc }>(action: () => Promise<T>) => Promise<T | undefined>;
  onClose: () => void;
  onDone: (text: string, checks: { text: string; step: string }[]) => void;
}) {
  const [file, setFile] = useState<{ name: string; data: string } | null>(null);
  const [book, setBook] = useState<TarifInspect>();
  const [sheet, setSheet] = useState(0);
  const [settings, setSettings] = useState<TarifSettings>();
  const [mode, setMode] = useState<"replace" | "add">("replace");
  const [preview, setPreview] = useState<TarifPreview>();
  const [busy, setBusy] = useState<"read" | "preview" | "apply" | null>(null);
  const [error, setError] = useState<string>();
  const input = useRef<HTMLInputElement>(null);

  const rows = book?.sheets[sheet]?.rows ?? [];
  const header = settings ? rows[settings.header_row] ?? [] : [];

  async function open(chosen: File) {
    setError(undefined);
    setPreview(undefined);
    setBusy("read");
    try {
      const [data, inspected] = await Promise.all([toBase64(chosen), api.tarifInspect(id, chosen)]);
      if (!inspected.sheets.length) throw new Error("В файле нет заполненных листов");
      setFile({ name: chosen.name, data });
      setBook(inspected);
      // лист, где догадка нашла больше всего: предмет, учителя или классы колонками
      const score = (g: TarifInspect["sheets"][number]["guess"]) =>
        g.class_columns.length + Object.values(g.mapping).filter((v) => v !== null).length;
      const best = inspected.sheets.reduce((top, s, n) => (score(s.guess) > score(inspected.sheets[top].guess) ? n : top), 0);
      pickSheet(inspected, best);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  function pickSheet(source: TarifInspect, index: number) {
    const guess = source.sheets[index].guess;
    setSheet(index);
    setSettings({ ...guess, fill_down: true, shorten: true });
  }

  const classColumnsOf = (row: string[]) => row.flatMap((text, c) => (CLASS_HEADER.test(text) ? [c] : []));
  const change = (patch: Partial<TarifSettings>) => setSettings((s) => (s ? { ...s, ...patch } : s));

  function setHeaderRow(index: number) {
    change({ header_row: index, class_columns: settings?.layout === "wide" ? classColumnsOf(rows[index] ?? []) : [] });
  }

  const body: TarifBody | null = file && book && settings
    ? { ...settings, file: file.data, sheet: book.sheets[sheet].name, mode } : null;

  // Предпросмотр пересчитывается сам после каждой правки настроек.
  useEffect(() => {
    if (!body) return;
    setBusy("preview");
    const timer = window.setTimeout(() => {
      api.tarifPreview(id, body)
        .then((p) => { setPreview(p); setError(undefined); })
        .catch((e) => setError(e instanceof Error ? e.message : String(e)))
        .finally(() => setBusy(null));
    }, 300);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [file, book, sheet, settings, mode]);

  async function load() {
    if (!body) return;
    setBusy("apply");
    const result = await run(() => api.tarifApply(id, body));
    setBusy(null);
    if (!result) return;
    const t = result.tarif;
    onDone([
      `Строк нагрузки из файла: ${t.rows}. Всего в нагрузке школы: ${t.load_rows}.`,
      t.classes.length ? `Заведены классы: ${t.classes.join(", ")}.` : "",
      t.subjects.length ? `Заведены предметы: ${t.subjects.join(", ")}.` : "",
      t.teachers.length ? `Заведено учителей: ${t.teachers.length}.` : "",
      t.split.length ? `Деление на подгруппы: ${t.split.length}.` : "",
    ].filter(Boolean).join(" "), t.checks);
  }

  const shownRows = settings ? rows.slice(Math.max(0, settings.header_row - 2), settings.header_row + 9) : [];
  const firstShown = settings ? Math.max(0, settings.header_row - 2) : 0;
  const width = Math.min(16, Math.max(0, ...rows.slice(0, 30).map((r) => r.length)));
  const roleOf = (column: number) => {
    if (!settings) return null;
    if (settings.layout === "wide" && settings.class_columns.includes(column)) return "класс";
    const field = FIELDS.find((f) => settings.mapping[f.key] === column && (settings.layout === "long" ? f.long : f.wide));
    return field?.label ?? null;
  };

  return (
    <Panel className="mt-4">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h2 className="text-heading">Импорт своей таблицы нагрузки</h2>
          <p className="mt-1 max-w-prose text-small text-pencil">
            Тарификационный список или любая таблица «кто что ведёт». Перепечатывать под шаблон не нужно: система
            угадает, где что, — поправьте, если ошиблась.
          </p>
        </div>
        <button type="button" className="text-small text-pen underline-offset-4 hover:underline" onClick={onClose}>скрыть</button>
      </div>

      {/* 1. Файл */}
      <div className="mt-5 flex flex-wrap items-center gap-3">
        <span className="text-small text-pencil">1</span>
        <Button variant={file ? "quiet" : "primary"} disabled={busy === "read"} onClick={() => input.current?.click()}>
          {busy === "read" ? "Читаю файл…" : file ? "Выбрать другой файл" : "Выбрать файл Excel"}
        </Button>
        <input ref={input} type="file" accept=".xlsx,.xls" className="hidden" aria-label="Файл таблицы нагрузки"
               onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) open(f); }} />
        {file && <span className="text-small">{file.name}</span>}
        {book && book.sheets.length > 1 && (
          <label className="flex items-center gap-2 text-small">
            Лист
            <select className={selectClass} value={sheet} onChange={(e) => pickSheet(book, Number(e.target.value))}>
              {book.sheets.map((s, n) => <option key={s.name} value={n}>{s.name}</option>)}
            </select>
          </label>
        )}
      </div>

      {error && <Notice tone="no" className="mt-4" title="Не получилось">{error}</Notice>}

      {settings && book && (
        <>
          {/* 2. Как устроена таблица */}
          <div className="mt-6 flex gap-3">
            <span className="text-small text-pencil">2</span>
            <div className="min-w-0 flex-1">
              <p className="font-semibold">Как устроена таблица</p>
              <div className="mt-3 flex flex-wrap items-end gap-6">
                <Segmented legend="Раскладка" value={settings.layout} options={LAYOUTS}
                           onChange={(layout) => change({ layout, class_columns: layout === "wide" ? classColumnsOf(header) : [] })} />
                <p className="max-w-md pb-1 text-small text-pencil">
                  {settings.layout === "wide"
                    ? "Строка — учитель и предмет, классы идут колонками, в ячейке часы."
                    : "Каждая строка — класс, предмет, учитель и часы."}
                </p>
              </div>

              <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {FIELDS.filter((f) => (settings.layout === "wide" ? f.wide : f.long)).map((field) => (
                  <label key={field.key} className="block text-small">
                    <span className="font-medium">{field.label}</span>
                    <select className={cx(inputClass, "mt-1")} value={settings.mapping[field.key] ?? ""}
                            onChange={(e) => change({ mapping: { ...settings.mapping,
                              [field.key]: e.target.value === "" ? null : Number(e.target.value) } })}>
                      <option value="">{field.key === "subgroup" ? "нет такой колонки" : "не выбрано"}</option>
                      {header.map((title, c) => (
                        <option key={c} value={c}>{letter(c)}{title ? `: ${title}` : ""}</option>
                      ))}
                    </select>
                  </label>
                ))}
              </div>

              {settings.layout === "wide" && (
                <div className="mt-4 text-small">
                  <p className="font-medium">Колонки с классами</p>
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {header.map((title, c) => title && (
                      <button key={c} type="button" aria-pressed={settings.class_columns.includes(c)}
                              onClick={() => change({ class_columns: settings.class_columns.includes(c)
                                ? settings.class_columns.filter((x) => x !== c) : [...settings.class_columns, c].sort((a, b) => a - b) })}
                              className={cx("rounded border px-2 py-0.5 transition-colors duration-150",
                                            settings.class_columns.includes(c) ? "border-pen bg-pen-soft text-pen" : "border-rule text-pencil hover:border-pencil")}>
                        {title}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              <div className="mt-4 flex flex-wrap gap-x-6 gap-y-2 text-small">
                <label className="flex cursor-pointer items-center gap-2">
                  <input type="checkbox" className="accent-pen" checked={settings.fill_down}
                         onChange={(e) => change({ fill_down: e.target.checked })} />
                  Пустое ФИО или предмет — как в строке выше
                </label>
                <label className="flex cursor-pointer items-center gap-2">
                  <input type="checkbox" className="accent-pen" checked={settings.shorten}
                         onChange={(e) => change({ shorten: e.target.checked })} />
                  ФИО полностью → «Фамилия И. О.»
                </label>
              </div>

              <p className="mt-5 text-small text-pencil">
                Начало листа «{book.sheets[sheet].name}». Щёлкните номер строки, если заголовки в другой.
              </p>
              <div className="mt-1.5 overflow-x-auto rounded border border-rule">
                <table className="border-collapse font-narrow text-cell">
                  <thead>
                    <tr className="bg-paper text-pencil">
                      <th className="w-12" />
                      {Array.from({ length: width }, (_, c) => (
                        <th key={c} className="min-w-[72px] border-l border-rule px-2 py-1 text-left font-normal">
                          {letter(c)}
                          {roleOf(c) && <span className="ml-1 font-medium text-pen">{roleOf(c)}</span>}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {shownRows.map((row, n) => {
                      const index = firstShown + n;
                      const isHeader = index === settings.header_row;
                      return (
                        <tr key={index} className={cx("border-t border-rule", isHeader && "bg-pen-soft font-semibold")}>
                          <th className="px-1">
                            <button type="button" onClick={() => setHeaderRow(index)}
                                    title="Это строка заголовков"
                                    className={cx("w-full rounded px-1.5 py-0.5 text-left font-normal", isHeader ? "text-pen" : "text-pencil hover:bg-paper")}>
                              {index + 1}
                            </button>
                          </th>
                          {Array.from({ length: width }, (_, c) => (
                            <td key={c} className={cx("max-w-[180px] truncate border-l border-rule px-2 py-1",
                                                      !isHeader && roleOf(c) && "bg-pen-soft/40")}>
                              {row[c] ?? ""}
                            </td>
                          ))}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          {/* 3. Что получится */}
          <div className="mt-6 flex gap-3">
            <span className="text-small text-pencil">3</span>
            <div className="min-w-0 flex-1">
              <p className="font-semibold">Что получится {busy === "preview" && <span className="font-normal text-pencil">— пересчитываю…</span>}</p>
              {preview && (
                <div className="mt-2 space-y-3 text-small">
                  <p className="text-body">
                    Строк нагрузки: <span className="font-semibold">{preview.total}</span>, уроков в неделю:{" "}
                    <span className="font-semibold">{preview.hours}</span>.
                  </p>
                  <ul className="space-y-1">
                    {preview.new.classes.length > 0 && <li>Новые классы: {preview.new.classes.join(", ")}.</li>}
                    {preview.new.teachers.length > 0 && (
                      <li>Новых учителей: {preview.new.teachers.length} — {preview.new.teachers.slice(0, 6).join(", ")}
                        {preview.new.teachers.length > 6 ? " и другие" : ""}</li>
                    )}
                    {preview.matched.length > 0 && (
                      <li>Узнал предметы: {preview.matched.map((m) => `«${m.from}» → ${m.to}`).join(", ")}.</li>
                    )}
                    {preview.unknown_subjects.length > 0 && (
                      <li className="text-worse">
                        Не узнал предметы, заведу как новые: {preview.unknown_subjects.join(", ")}. Если это сокращение
                        знакомого предмета — поправьте название в файле.
                      </li>
                    )}
                    {preview.split.length > 0 && (
                      <li>Деление на подгруппы, один предмет у двух учителей: {preview.split.join("; ")}</li>
                    )}
                    {preview.no_teacher > 0 && <li className="text-worse">Строк без учителя: {preview.no_teacher} — назначите потом.</li>}
                    {preview.skipped_total > 0 && (
                      <li>
                        <details>
                          <summary className="cursor-pointer">Пропущено строк: {preview.skipped_total}</summary>
                          <ul className="mt-1 list-disc pl-5 text-pencil">
                            {preview.skipped.map((s, n) => <li key={n}>строка {s.row}: {s.reason}</li>)}
                          </ul>
                        </details>
                      </li>
                    )}
                  </ul>

                  {preview.rows.length > 0 && (
                    <div className="overflow-x-auto">
                      <table className="w-full min-w-[520px] border-collapse text-left">
                        <thead>
                          <tr className="border-b border-ink/30">
                            {["Класс", "Предмет", "Учитель", "Часов", "Подгруппа", "Строка"].map((h) => (
                              <th key={h} className="py-1.5 pr-3 font-semibold">{h}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {preview.rows.slice(0, 12).map((r, n) => (
                            <tr key={n} className="border-b border-rule">
                              <td className="py-1 pr-3">{r.класс}</td>
                              <td className="py-1 pr-3">{r.предмет}</td>
                              <td className="py-1 pr-3">{r.учитель || <span className="text-worse">нет</span>}</td>
                              <td className="py-1 pr-3 tabular-nums">{r.часов}</td>
                              <td className="py-1 pr-3">{r.подгруппа}</td>
                              <td className="py-1 text-pencil">{r.row}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      {preview.total > 12 && <p className="mt-1 text-pencil">и ещё {preview.total - 12} строк</p>}
                    </div>
                  )}

                  <div className="flex flex-wrap items-end gap-4 pt-2">
                    <Segmented legend="Что сделать с нынешней нагрузкой" value={mode} options={MODES} onChange={setMode} />
                    <Button variant="primary" disabled={!preview.total || busy === "apply"} onClick={load}>
                      {busy === "apply" ? "Загружаю…" : `Загрузить нагрузку: ${preview.total} строк`}
                    </Button>
                  </div>
                  <p className="max-w-prose text-pencil">
                    {mode === "replace"
                      ? "Нынешняя нагрузка школы заменится этой — прежняя останется в истории. Классы, предметы и учителя не удаляются, недостающие заведутся."
                      : "Строки добавятся к нынешней нагрузке; та же строка (класс, предмет, учитель, подгруппа) возьмёт часы из файла."}
                  </p>
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </Panel>
  );
}
