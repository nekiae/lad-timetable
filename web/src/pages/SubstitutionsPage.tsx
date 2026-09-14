import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";

import { api, type Need, type Schedule } from "../api";
import { Button, ButtonLink, EmptyState, Field, Notice, Panel, cx, inputClass } from "../ui";

const LEVEL = { best: "ведёт этот предмет", good: "знает класс", possible: "свободен в этот час" };

function localToday() {
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 10);
}

// Замены. Утром завуч узнаёт, что учитель заболел: выбирает его и дату,
// система на каждый урок предлагает кандидатов с причинами (lad/substitute.py),
// лучший уже отмечен. Итог — лист замен на печать, как его вешают в учительской.
export function SubstitutionsPage() {
  const { id = "" } = useParams();
  const [schedule, setSchedule] = useState<Schedule | null>();
  const [absent, setAbsent] = useState("");
  const [date, setDate] = useState(localToday());
  const [needs, setNeeds] = useState<Need[]>();
  const [picked, setPicked] = useState<Record<number, string>>({});
  const [hideNames, setHideNames] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();

  useEffect(() => {
    api.latest(id).then(setSchedule).catch(() => setSchedule(null));
  }, [id]);

  const dir = schedule?.directory;
  const teachers = useMemo(
    () => (dir ? Object.entries(dir.teachers).sort((a, b) => a[1].localeCompare(b[1], "ru")) : []), [dir]);

  if (schedule === undefined) return <p className="px-4 py-10 text-pencil md:px-8">Загружаю расписание…</p>;
  if (!schedule || !dir)
    return (
      <EmptyState text="Замены подбираются по составленному расписанию, а его ещё нет."
                  action={<ButtonLink to={`/s/${id}`} variant="primary">Перейти к составлению</ButtonLink>} />
    );

  const order = new Map(Object.keys(dir.teachers).map((t, i) => [t, i + 1]));
  const nameOf = (tid: string) => (hideNames ? `Учитель ${order.get(tid)}` : dir.teachers[tid] ?? tid);
  const noon = date ? new Date(`${date}T12:00:00`) : null;
  const day = noon ? dir.days.find((d) => d.n === noon.getDay()) : undefined;
  const dateText = noon?.toLocaleDateString("ru-RU", { weekday: "long", day: "numeric", month: "long" }) ?? "";

  const reset = () => {
    setNeeds(undefined);
    setPicked({});
  };

  async function find() {
    if (!day) return;
    setBusy(true);
    setError(undefined);
    try {
      const result = await api.substitutions(id, absent, day.n, schedule!.lessons);
      setNeeds(result.needs);
      setPicked(Object.fromEntries(result.needs.filter((n) => n.candidates[0])
        .map((n) => [n.index, n.candidates[0].teacher_id])));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="px-4 py-8 md:px-8">
      <div className="max-w-5xl print:hidden">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-title">Замены</h1>
            <p className="mt-1 max-w-prose text-pencil">
              Учитель заболел или уехал на курсы — система подберёт, кто проведёт его уроки, и объяснит почему.
            </p>
          </div>
          <label className="flex cursor-pointer items-center gap-2 text-small">
            <input type="checkbox" className="accent-pen" checked={hideNames}
                   onChange={(e) => setHideNames(e.target.checked)} />
            Скрыть ФИО учителей
          </label>
        </div>

        <div className="mt-6 flex flex-wrap items-end gap-4">
          <Field label="Кто отсутствует" className="w-full max-w-sm">
            <select className={inputClass} value={absent} onChange={(e) => { setAbsent(e.target.value); reset(); }}>
              <option value="">Выберите учителя</option>
              {teachers.map(([tid]) => <option key={tid} value={tid}>{nameOf(tid)}</option>)}
            </select>
          </Field>
          <Field label="Когда" className="w-full max-w-[12rem]">
            <input type="date" className={inputClass} value={date} onChange={(e) => { setDate(e.target.value); reset(); }} />
          </Field>
          <Button variant="primary" disabled={!absent || !day || busy} onClick={find}>
            {busy ? "Подбираю…" : "Подобрать замены"}
          </Button>
        </div>

        {date && !day && (
          <Notice tone="info" className="mt-4" title="В этот день уроков нет">Выберите учебный день.</Notice>
        )}
        {error && <Notice tone="no" className="mt-4" title="Замены не подобрались">{error}</Notice>}
        {needs && needs.length === 0 && day && (
          <Notice tone="ok" className="mt-6" title={`В этот день (${day.name.toLowerCase()}) у учителя уроков нет`}>
            Замены не нужны.
          </Notice>
        )}

        {needs && needs.length > 0 && (
          <ol className="mt-8 space-y-4">
            {needs.map((need) => (
              <li key={need.index}>
                <Panel as="div">
                  <p className="text-heading">{need.period}-й урок, {need.group_name}, {need.subject}</p>
                  {(need.room_id || need.note) && (
                    <p className="mt-0.5 text-small text-pencil">
                      {need.room_id ? `Кабинет ${need.room_id}. ` : ""}{need.note}
                    </p>
                  )}
                  {need.candidates.length === 0 && (
                    <p className="mt-3 text-no">Свободных учителей в этот час нет.</p>
                  )}
                  <div role="radiogroup" aria-label={`Замена на ${need.period}-й урок`}
                       className="mt-3 grid gap-2 md:grid-cols-2">
                    {need.candidates.map((c) => {
                      const on = picked[need.index] === c.teacher_id;
                      return (
                        <button key={c.teacher_id} type="button" role="radio" aria-checked={on}
                                onClick={() => setPicked({ ...picked, [need.index]: c.teacher_id })}
                                className={cx("rounded border px-3 py-2 text-left text-small transition-colors duration-150",
                                              on ? "border-pen bg-pen-soft" : "border-rule bg-sheet hover:border-pencil")}>
                          <span className="flex flex-wrap items-baseline justify-between gap-x-3">
                            <span className="text-body font-semibold">{nameOf(c.teacher_id)}</span>
                            <span className={c.level === "best" ? "text-ok" : "text-pencil"}>{LEVEL[c.level]}</span>
                          </span>
                          {c.reasons.map((r) => <span key={r} className="block text-ink/80">{r}</span>)}
                          {c.costs.map((r) => <span key={r} className="block text-worse">{r}</span>)}
                        </button>
                      );
                    })}
                    <button type="button" role="radio" aria-checked={picked[need.index] === ""}
                            onClick={() => setPicked({ ...picked, [need.index]: "" })}
                            className={cx("rounded border border-dashed px-3 py-2 text-left text-small transition-colors duration-150",
                                          picked[need.index] === "" ? "border-pen bg-pen-soft" : "border-rule hover:border-pencil")}>
                      <span className="text-body font-semibold">Не заменять</span>
                      <span className="block text-pencil">Урок не проводится</span>
                    </button>
                  </div>
                </Panel>
              </li>
            ))}
          </ol>
        )}
      </div>

      {needs && needs.length > 0 && (
        <section className="mt-10 max-w-5xl print:mt-0">
          <div className="flex flex-wrap items-baseline justify-between gap-3 print:hidden">
            <h2 className="text-heading">Лист замен</h2>
            <Button onClick={() => window.print()}>Распечатать лист замен</Button>
          </div>
          <div className="mt-3 rounded-lg border border-rule bg-sheet p-6 print:border-0 print:p-0">
            <p className="text-heading">Замены на {dateText}</p>
            <p className="text-small text-pencil">{dir.name}. Отсутствует: {nameOf(absent)}.</p>
            <div className="mt-4 overflow-x-auto">
              <table className="w-full border-collapse text-small">
                <thead>
                  <tr className="border-b border-ink/30 text-left">
                    <th className="py-2 pr-4">Урок</th>
                    <th className="py-2 pr-4">Класс</th>
                    <th className="py-2 pr-4">Предмет</th>
                    <th className="py-2 pr-4">Кабинет</th>
                    <th className="py-2">Заменяет</th>
                  </tr>
                </thead>
                <tbody>
                  {needs.map((need) => (
                    <tr key={need.index} className="border-b border-rule">
                      <td className="py-2 pr-4">{need.period}</td>
                      <td className="py-2 pr-4">{need.group_name}</td>
                      <td className="py-2 pr-4">{need.subject}</td>
                      <td className="py-2 pr-4">{need.room_id ?? ""}</td>
                      <td className={cx("py-2", !picked[need.index] && "text-pencil")}>
                        {picked[need.index] ? nameOf(picked[need.index]) : "урок не проводится"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-8 text-small text-pencil">Заместитель директора ______________________</p>
          </div>
        </section>
      )}
    </div>
  );
}
