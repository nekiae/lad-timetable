import { useState } from "react";

import { api } from "../../api";
import { Button, Notice, Segmented, cx, inputClass } from "../../ui";
import { DataTable, type Row } from "../../ui/DataTable";
import type { StepProps } from "./DataPage";

const text = (v: unknown) => (v === null || v === undefined ? "" : String(v).trim());
const optional = (v: unknown) => {
  const s = text(v);
  return s && s !== "—" && s.toLowerCase() !== "nan" ? s : "";
};
const labelOf = (r: Row) => (text(r["подгруппа"]) ? `${text(r["класс"])} (${text(r["подгруппа"])})` : text(r["класс"]));
const surname = (full: string) => full.split(" ")[0];

// Нагрузка. Построчно её не вводят: у школы на 24 класса это 400+ строк,
// где класс, предмет и часы уже известны из типового плана. Вписать нужно
// только, кто ведёт. Поэтому главный режим перевёрнут: выбираем предмет
// и раздаём его классы учителям (логика — lad.tables.assign_teacher).
export function LoadStep(props: StepProps) {
  const { schoolId, doc, run } = props;
  const load = doc.tables.load ?? [];
  const [mode, setMode] = useState<"assign" | "table">("assign");
  const [unknown, setUnknown] = useState<string[]>([]);

  if (load.length === 0)
    return (
      <div>
        <p className="max-w-prose">
          Черновик строится по типовому учебному плану (постановление Минобразования № 75): каждому классу —
          его предметы и часы. Останется назначить учителей.
        </p>
        <Button variant="primary" className="mt-4" onClick={async () => {
          const r = await run(() => api.loadFromPlan(schoolId));
          if (r) setUnknown(r.unknown);
        }}>
          Составить черновик нагрузки по плану
        </Button>
      </div>
    );

  return (
    <div className="space-y-6">
      {unknown.length > 0 && (
        <Notice tone="worse" title="Часы этих предметов в плане заданы дробью по полугодиям">
          Впишите их сами в полной таблице: {unknown.slice(0, 8).join("; ")}
        </Notice>
      )}
      <Segmented legend="Как вводить" value={mode} onChange={setMode}
                 options={[{ value: "assign", label: "Назначить учителей" }, { value: "table", label: "Полная таблица" }]} />
      {mode === "assign" ? <Assign {...props} /> : <FullTable {...props} onUnknown={setUnknown} />}
    </div>
  );
}

function Assign({ schoolId, doc, input, run }: StepProps) {
  const load = doc.tables.load ?? [];
  const teachers = (doc.tables.teachers ?? []).map((r) => text(r["ФИО"])).filter(Boolean);
  const classes = (doc.tables.classes ?? []).map((r) => text(r["класс"])).filter(Boolean);

  const bySubject = new Map<string, Row[]>();
  for (const row of load) {
    const s = text(row["предмет"]);
    if (s) bySubject.set(s, [...(bySubject.get(s) ?? []), row]);
  }
  const progress = [...bySubject.entries()]
    .map(([subject, rows]) => ({ subject, left: rows.filter((r) => !optional(r["учитель"])).length, total: rows.length }))
    .sort((a, b) => Number(a.left === 0) - Number(b.left === 0) || a.subject.localeCompare(b.subject, "ru"));
  const assigned = progress.reduce((n, p) => n + p.total - p.left, 0);
  const totalSlots = progress.reduce((n, p) => n + p.total, 0);

  const [subject, setSubject] = useState(progress[0]?.subject ?? "");
  const [newTeacher, setNewTeacher] = useState("");
  const [pool, setPool] = useState<string[] | null>(null);
  const [pending, setPending] = useState<{ teacher: string; classes: string[]; previous?: string; skipped: string[] }>();
  const [hours, setHours] = useState<number>();
  const [showFresh, setShowFresh] = useState(false);

  const slots = (bySubject.get(subject) ?? []).map((r) => ({
    label: labelOf(r), className: text(r["класс"]), teacher: optional(r["учитель"]),
  }));
  const divided = input.divided.includes(subject);
  const current = [...new Set(slots.map((s) => s.teacher).filter(Boolean))].sort((a, b) => a.localeCompare(b, "ru"));
  const withSlot = new Set(slots.map((s) => s.className));
  const fresh = classes.filter((c) => !withSlot.has(c));
  const free = slots.filter((s) => !s.teacher);

  async function assign(teacher: string, chosen: string[], previous?: string, extraHours?: number) {
    const r = await run(() => api.assign(schoolId, { subject, teacher, classes: chosen, previous, hours: extraHours ?? null }));
    if (r?.skipped.length) setPending({ teacher, classes: chosen, previous, skipped: r.skipped });
    else setPending(undefined);
    if (teacher === newTeacher) setNewTeacher("");
  }

  function toggle(teacher: string, label: string) {
    const mine = slots.filter((s) => s.teacher === teacher).map((s) => s.label);
    assign(teacher, mine.includes(label) ? mine.filter((l) => l !== label) : [...mine, label]);
  }

  const chosenPool = pool ?? current;

  return (
    <div className="grid gap-8 lg:grid-cols-[14rem_1fr]">
      <div>
        <p className="text-small text-pencil">Назначено {assigned} из {totalSlots}</p>
        <div className="mt-2 h-1 overflow-hidden rounded-full bg-rule">
          <div className="h-full bg-pen" style={{ width: `${totalSlots ? (assigned / totalSlots) * 100 : 0}%` }} />
        </div>
        <ul className="mt-4 space-y-0.5 max-lg:flex max-lg:flex-wrap max-lg:gap-1 max-lg:space-y-0">
          {progress.map((p) => (
            <li key={p.subject}>
              <button type="button" onClick={() => { setSubject(p.subject); setPool(null); setPending(undefined); setShowFresh(false); }}
                      aria-current={p.subject === subject ? "true" : undefined}
                      className={cx("flex w-full items-baseline gap-2 rounded px-2 py-1.5 text-left text-small transition-colors duration-150",
                                    p.subject === subject ? "bg-pen-soft text-pen" : "hover:bg-sheet")}>
                <span className="min-w-0 truncate font-medium" title={p.subject}>{p.subject}</span>
                <span className={cx("ml-auto shrink-0", p.left ? "text-worse" : "text-pencil")}>
                  {p.left ? `осталось ${p.left}` : "готово"}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </div>

      <div className="min-w-0 space-y-6">
        <div>
          <h3 className="text-heading">{subject}</h3>
          <p className="mt-1 max-w-prose text-small text-pencil">
            Щёлкните класс, чтобы закрепить его за учителем. Класс, который уже ведёт другой, перейдёт к этому.
            {divided && " У предмета деление: подгруппы (1) и (2) одного класса должны вести разные учителя."}
          </p>
          {/* Классы, где предмета нет, спрятаны: у астрономии это 22 лишние
              кнопки под каждым учителем, а заводят предмет в новом классе редко. */}
          {fresh.length > 0 && (
            <button type="button" onClick={() => setShowFresh(!showFresh)}
                    className="mt-2 text-small text-pen underline-offset-4 hover:underline">
              {showFresh ? "Скрыть классы без этого предмета" : `Завести предмет ещё в каком-то классе (${fresh.length} без него)`}
            </button>
          )}
        </div>

        {pending && (
          <Notice tone="worse" title={`Типовой план не задаёт часы «${subject}» для: ${pending.skipped.join(", ")}`}>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <input type="number" min={1} max={12} aria-label="Часов в неделю" className={`${inputClass} max-w-[6rem]`}
                     value={hours ?? ""} onChange={(e) => setHours(Number(e.target.value))} />
              <span>часов в неделю</span>
              <Button disabled={!hours} onClick={() => assign(pending.teacher, pending.classes, pending.previous, hours)}>
                Завести с этими часами
              </Button>
            </div>
          </Notice>
        )}

        <ul className="space-y-5">
          {[...current, ""].map((teacher) => {
            const who = teacher || newTeacher;
            const mine = slots.filter((s) => s.teacher === who).map((s) => s.label);
            const total = input.teacher_hours[who] ?? 0;
            return (
              <li key={teacher || "new"} className="border-t border-rule pt-4 first:border-t-0 first:pt-0">
                <div className="flex flex-wrap items-center gap-3">
                  <select aria-label="Учитель" className={`${inputClass} max-w-sm`} value={who}
                          onChange={(e) => {
                            if (teacher && e.target.value) assign(e.target.value, mine, teacher);
                            else setNewTeacher(e.target.value);
                          }}>
                    <option value="">{teacher ? "—" : "Добавить учителя…"}</option>
                    {teachers.map((t) => <option key={t} value={t}>{t}</option>)}
                  </select>
                  {who && (
                    <span className={cx("text-small", total > 30 ? "text-worse" : "text-pencil")}>
                      {total} ч в неделю{total > 30 ? " — больше полутора ставок" : ""}
                    </span>
                  )}
                </div>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {slots.map((s) => {
                    const own = s.teacher === who && Boolean(who);
                    return (
                      <button key={s.label} type="button" disabled={!who} aria-pressed={own}
                              title={s.teacher && !own ? `Сейчас ведёт ${s.teacher}` : undefined}
                              onClick={() => toggle(who, s.label)}
                              className={cx("rounded border px-2 py-1 text-left text-small leading-tight transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-50",
                                            own ? "border-pen bg-pen text-white"
                                              : s.teacher ? "border-rule bg-paper text-pencil hover:border-pencil"
                                                : "border-rule bg-sheet hover:border-pen")}>
                        <span className="font-medium">{s.label}</span>
                        {s.teacher && !own && <span className="block text-[11px]">{surname(s.teacher)}</span>}
                      </button>
                    );
                  })}
                  {showFresh && fresh.map((c) => (
                    <button key={c} type="button" disabled={!who} onClick={() => assign(who, [...mine, c])}
                            title="Предмета у этого класса ещё нет — щелчок заведёт его"
                            className="rounded border border-dashed border-rule px-2 py-1 text-small text-pencil hover:border-pen hover:text-ink disabled:cursor-not-allowed disabled:opacity-50">
                      + {c}
                    </button>
                  ))}
                </div>
              </li>
            );
          })}
        </ul>

        {free.length > 0 ? (
          <div className="rounded-lg border border-rule bg-sheet p-4">
            <p className="font-medium">Без учителя: {free.length}</p>
            <p className="mt-1 text-small text-pencil">
              Система разложит свободные классы так, чтобы часы у выбранных учителей вышли примерно поровну.
              Потом можно поправить пару классов щелчком.
            </p>
            <div className="mt-3 flex flex-wrap gap-1.5">
              {teachers.filter((t) => current.includes(t) || chosenPool.includes(t)).map((t) => (
                <button key={t} type="button" aria-pressed={chosenPool.includes(t)}
                        onClick={() => setPool(chosenPool.includes(t) ? chosenPool.filter((x) => x !== t) : [...chosenPool, t])}
                        className={cx("rounded border px-2 py-1 text-small",
                                      chosenPool.includes(t) ? "border-pen bg-pen-soft text-pen" : "border-rule bg-sheet")}>
                  {t}
                </button>
              ))}
            </div>
            {current.length === 0 && (
              <p className="mt-2 text-small text-pencil">Назначьте хотя бы одного учителя выше — между кем делить, система не угадает.</p>
            )}
            <Button className="mt-3" disabled={!chosenPool.length}
                    onClick={() => run(() => api.spread(schoolId, subject, chosenPool))}>
              Разложить поровну
            </Button>
          </div>
        ) : (
          slots.length > 0 && <p className="text-small text-ok">Все классы предмета закреплены за учителями.</p>
        )}
      </div>
    </div>
  );
}

function FullTable({ schoolId, doc, input, setRows, run, onUnknown }: StepProps & { onUnknown: (u: string[]) => void }) {
  const pick = (table: string, key: string) => (doc.tables[table] ?? []).map((r) => text(r[key])).filter(Boolean);
  return (
    <div className="space-y-4">
      <Button onClick={async () => {
        const r = await run(() => api.loadFromPlan(schoolId));
        if (r) onUnknown(r.unknown);
      }}>
        Добавить недостающие строки по плану
      </Button>
      <DataTable rows={doc.tables.load ?? []} onChange={(r) => setRows("load", r)} addLabel="Добавить строку нагрузки" columns={[
        { key: "класс", label: "Класс", type: "select", options: pick("classes", "класс"), width: "w-24" },
        { key: "предмет", label: "Предмет", type: "select", options: pick("subjects", "предмет") },
        { key: "учитель", label: "Учитель", type: "select", options: ["", ...pick("teachers", "ФИО")] },
        { key: "часов", label: "Часов", type: "number", width: "w-20" },
        { key: "подгруппа", label: "Подгруппа", width: "w-24", title: "«1» и «2» при делении класса, иначе пусто." },
        { key: "уровень", label: "Уровень", type: "select", options: input.options.levels, width: "w-32" },
        { key: "тип", label: "Тип", type: "select", options: input.options.lesson_kinds, width: "w-36" },
        { key: "кабинет", label: "Кабинет", type: "select", options: ["—", ...input.options.room_kinds], width: "w-40",
          title: "Только когда подгруппы расходятся по разным кабинетам (труд). Иначе «—»." },
      ]} />
    </div>
  );
}
