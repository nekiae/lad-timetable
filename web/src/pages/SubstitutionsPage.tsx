import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";

import { api, saveBlob, type Journal, type JournalEntry, type Need, type Schedule, type SheetDTO } from "../api";
import { useHideNames } from "../hideNames";
import { Button, ButtonLink, EmptyState, Field, Notice, Panel, cx, inputClass } from "../ui";
import { SubstitutionJournal } from "./SubstitutionJournal";

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
  const [hideNames] = useHideNames();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  // Что сейчас готовится файлом — кнопка показывает это, а не молчит секунду.
  const [exporting, setExporting] = useState<"pdf" | "xlsx" | "share" | null>(null);
  const [copied, setCopied] = useState(false);
  // «Отправить» — только где браузер умеет делиться файлом (телефон, Safari).
  const canShare = useMemo(() => {
    try {
      return typeof navigator.share === "function"
        && Boolean(navigator.canShare?.({ files: [new File([""], "zameny.pdf", { type: "application/pdf" })] }));
    } catch {
      return false;
    }
  }, []);

  useEffect(() => {
    api.latest(id).then(setSchedule).catch(() => setSchedule(null));
  }, [id]);

  // Журнал замен: сохранённые замены по датам и итог месяца (server/journal.py).
  const [month, setMonth] = useState(localToday().slice(0, 7));
  const [journal, setJournal] = useState<Journal>();
  // Запись журнала на выбранные дату и учителя, если её уже сохраняли.
  const [savedEntry, setSavedEntry] = useState<JournalEntry | null>(null);
  const [journalState, setJournalState] = useState<"idle" | "saving" | "saved">("idle");
  const loadJournal = (m: string) => api.journal(id, m).then(setJournal).catch(() => setJournal(undefined));
  useEffect(() => {
    if (/^\d{4}-\d{2}$/.test(month)) loadJournal(month);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, month]);

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
    setSavedEntry(null);
    setJournalState("idle");
  };
  const byName = new Map(Object.entries(dir.teachers).map(([tid, name]) => [name, tid]));
  // В журнале — имена; при «Скрыть ФИО» показываем тот же «Учитель N», что и в листе.
  const shownName = (name: string) => (hideNames ? (byName.has(name) ? nameOf(byName.get(name)!) : "Учитель") : name);

  // Лист замен один на все выходы: экран, PDF, Excel и текст для чата собираются
  // из одних строк, чтобы в файле стояло ровно то, что завуч выбрал на экране.
  // Точка в конце ФИО («Бондарь С. Л.») не удваивается точкой предложения.
  const absentName = absent ? nameOf(absent).replace(/\.$/, "") : "";
  const sheet: SheetDTO | null = needs && needs.length > 0 ? {
    title: `Замены на ${dateText}`,
    subtitle: `${dir.name}. Отсутствует: ${absentName}.`,
    rows: needs.map((need) => [String(need.period), need.group_name, need.subject, need.room_id ?? "",
                               picked[need.index] ? nameOf(picked[need.index]) : "урок не проводится"]),
  } : null;
  const fileName = (ext: string) => `zameny-${date}.${ext}`;

  async function download(format: "pdf" | "xlsx") {
    if (!sheet) return;
    setExporting(format);
    setError(undefined);
    try {
      saveBlob(await api.substitutionSheet(id, format, sheet), fileName(format));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setExporting(null);
    }
  }

  async function saveJournal() {
    if (!needs) return;
    setJournalState("saving");
    try {
      const entry = await api.saveJournal(id, {
        date,
        absent: dir!.teachers[absent],
        rows: needs.map((n) => ({ period: n.period, group: n.group_name, subject: n.subject, room: n.room_id ?? "",
                                  substitute: picked[n.index] ? dir!.teachers[picked[n.index]] : "" })),
      });
      setSavedEntry(entry);
      setJournalState("saved");
      if (date.slice(0, 7) === month) loadJournal(month);
      else setMonth(date.slice(0, 7));
    } catch (e) {
      setJournalState("idle");
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  function openEntry(entry: JournalEntry) {
    const tid = byName.get(entry.absent);
    if (!tid) {
      setError(`Учителя «${entry.absent}» больше нет в данных школы — эту запись можно только скачать в Excel.`);
      return;
    }
    setAbsent(tid);
    setDate(entry.date);
    window.scrollTo({ top: 0, behavior: "smooth" });
    find(tid, entry.date);
  }

  async function removeEntry(entry: JournalEntry) {
    await api.deleteJournal(id, entry.id);
    if (savedEntry?.id === entry.id) {
      setSavedEntry(null);
      setJournalState("idle");
    }
    loadJournal(month);
  }

  async function copyText() {
    if (!sheet) return;
    const lines = sheet.rows.map(([period, group, subject, room, who]) =>
      `${period}-й урок, ${group}, ${subject}${room ? `, каб. ${room}` : ""} — ${who}`);
    await navigator.clipboard.writeText([sheet.title, `Отсутствует: ${nameOf(absent)}`, "", ...lines].join("\n"));
    setCopied(true);
    window.setTimeout(() => setCopied(false), 2000);
  }

  async function share() {
    if (!sheet) return;
    setExporting("share");
    try {
      const file = new File([await api.substitutionSheet(id, "pdf", sheet)], fileName("pdf"), { type: "application/pdf" });
      await navigator.share({ files: [file], title: sheet.title });
    } catch (e) {
      if (!(e instanceof DOMException && e.name === "AbortError")) setError(e instanceof Error ? e.message : String(e));
    } finally {
      setExporting(null);
    }
  }

  // Подобрать замены. Если на эту дату и учителя замены уже сохранены в журнале —
  // выбор берётся из журнала, а не заново «лучший кандидат»: завуч мог поменять
  // его утром, и повторное открытие не должно молча переписать решение.
  async function find(teacherId = absent, onDate = date) {
    const at = onDate ? new Date(`${onDate}T12:00:00`) : null;
    const onDay = at ? dir!.days.find((d) => d.n === at.getDay()) : undefined;
    if (!teacherId || !onDay) return;
    setBusy(true);
    setError(undefined);
    try {
      const [result, saved] = await Promise.all([
        api.substitutions(id, teacherId, onDay.n, schedule!.lessons),
        api.journal(id, onDate.slice(0, 7)),
      ]);
      const entry = saved.days.find((e) => e.date === onDate && e.absent === dir!.teachers[teacherId]) ?? null;
      setNeeds(result.needs);
      setSavedEntry(entry);
      setJournalState(entry ? "saved" : "idle");
      setPicked(Object.fromEntries(result.needs.flatMap((n) => {
        const row = entry?.rows.find((r) => r.period === n.period && r.group === n.group_name && r.subject === n.subject);
        if (row) return [[n.index, row.substitute ? byName.get(row.substitute) ?? "" : ""]];
        return n.candidates[0] ? [[n.index, n.candidates[0].teacher_id]] : [];
      })));
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
          <Button variant="primary" disabled={!absent || !day || busy} onClick={() => find()}>
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
                                onClick={() => {
                                  setPicked({ ...picked, [need.index]: c.teacher_id });
                                  setJournalState("idle");
                                }}
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
                            onClick={() => {
                              setPicked({ ...picked, [need.index]: "" });
                              setJournalState("idle");
                            }}
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
          <div className="flex flex-wrap items-center justify-between gap-3 print:hidden">
            <h2 className="text-heading">Лист замен</h2>
            <div className="flex flex-wrap gap-2">
              <Button variant="primary" disabled={journalState !== "idle"} onClick={saveJournal}>
                {journalState === "saved" ? "Сохранено в журнал" : journalState === "saving" ? "Сохраняю…"
                  : savedEntry ? "Обновить в журнале" : "Сохранить в журнал"}
              </Button>
              <Button disabled={exporting !== null} onClick={() => download("pdf")}>
                {exporting === "pdf" ? "Готовлю PDF…" : "Скачать PDF"}
              </Button>
              <Button disabled={exporting !== null} onClick={() => download("xlsx")}>
                {exporting === "xlsx" ? "Готовлю Excel…" : "Скачать Excel"}
              </Button>
              <Button onClick={copyText}>{copied ? "Скопировано" : "Скопировать для чата"}</Button>
              {canShare && (
                <Button disabled={exporting !== null} onClick={share}>
                  {exporting === "share" ? "Готовлю…" : "Отправить"}
                </Button>
              )}
              <Button onClick={() => window.print()}>Распечатать</Button>
            </div>
          </div>
          <div className="mt-3 rounded-lg border border-rule bg-sheet p-6 print:border-0 print:p-0">
            <p className="text-heading">Замены на {dateText}</p>
            <p className="text-small text-pencil">{sheet?.subtitle}</p>
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

      {savedEntry && journalState === "saved" && needs && needs.length > 0 && (
        <p className="mt-3 max-w-5xl text-small text-pencil print:hidden">
          Замены на эту дату сохранены в журнале — выбор выше взят оттуда.
        </p>
      )}

      <SubstitutionJournal journal={journal} month={month} onMonth={setMonth} shownName={shownName}
                           opened={savedEntry?.id ?? null} onOpen={openEntry} onDelete={removeEntry}
                           onDownload={async () => saveBlob(await api.journalXlsx(id, month), `zameny-${month}.xlsx`)} />
    </div>
  );
}
