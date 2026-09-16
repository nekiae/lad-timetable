import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { api, saveBlob, type Directory, type LessonDTO, type Schedule } from "../api";
import { useHideNames } from "../hideNames";
import { Button, EmptyState, Segmented, cx } from "../ui";

type By = "class" | "teacher";

// Печать: лист A4 на класс или на учителя. Общая сетка на 24 класса на бумагу
// не ложится, а в школе расписание и не висит одной простынёй: у кабинета —
// лист класса, в учительской — листы учителей. Страница вне шапки приложения,
// чтобы печаталось только расписание.
export function PrintPage() {
  const { id = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const by: By = params.get("by") === "teacher" ? "teacher" : "class";
  const [schedule, setSchedule] = useState<Schedule | null>();
  // Печать открывается вне общей шапки, поэтому переключатель остаётся на самой
  // странице, но состояние — общее: выбор, сделанный в приложении, здесь виден.
  const [hideNames, setHideNames] = useHideNames();
  const [exporting, setExporting] = useState<"pdf" | "xlsx" | null>(null);
  const [error, setError] = useState<string>();

  useEffect(() => {
    api.latest(id).then(setSchedule).catch(() => setSchedule(null));
  }, [id]);

  if (schedule === undefined) return <p className="px-4 py-10 text-pencil md:px-8">Загружаю расписание…</p>;
  if (!schedule)
    return <EmptyState text="Печатать нечего: расписание ещё не составлено." />;

  const dir = schedule.directory;
  const order = new Map(Object.keys(dir.teachers).map((t, i) => [t, i + 1]));
  const teacherName = (tid: string) => (hideNames ? `Учитель ${order.get(tid)}` : dir.teachers[tid] ?? tid);
  const surname = (tid: string) => (hideNames ? teacherName(tid) : teacherName(tid).split(" ")[0]);

  // PDF — все листы одним файлом, собирает сервер; Excel — книга расписания
  // (классы, учителя, кабинеты), та же, что на экране расписания.
  async function download(format: "pdf" | "xlsx") {
    setExporting(format);
    setError(undefined);
    try {
      if (format === "pdf")
        saveBlob(await api.printPdf(id, by, hideNames), by === "class" ? "raspisanie-po-klassam.pdf" : "raspisanie-po-uchitelyam.pdf");
      else await api.exportXlsx(id, schedule!.lessons, hideNames);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setExporting(null);
    }
  }

  const sheets = by === "class"
    ? dir.classes.map((c) => ({
        key: c.id, title: c.name,
        lessons: schedule.lessons.filter((l) => dir.groups[l.group_id]?.class_ids.includes(c.id)),
      }))
    : Object.keys(dir.teachers)
        .sort((a, b) => teacherName(a).localeCompare(teacherName(b), "ru"))
        .map((tid) => ({ key: tid, title: teacherName(tid), lessons: schedule.lessons.filter((l) => l.teacher_id === tid) }))
        .filter((s) => s.lessons.length > 0);

  return (
    <div className="px-4 py-8 md:px-8 print:p-0">
      <div className="mb-8 flex flex-wrap items-end justify-between gap-4 print:hidden">
        <div>
          <Link to={`/s/${id}/schedule`} className="text-small text-pen underline-offset-4 hover:underline">
            Вернуться к расписанию
          </Link>
          <h1 className="mt-2 text-title">Печать расписания</h1>
          <p className="mt-1 text-pencil">
            {sheets.length} листов A4. В файл и на печать идёт последняя сохранённая версия.
          </p>
        </div>
        <div className="flex flex-wrap items-end gap-4">
          <Segmented legend="Листы" value={by} onChange={(v) => setParams({ by: v })}
                     options={[{ value: "class", label: "По классам" }, { value: "teacher", label: "По учителям" }]} />
          <label className="flex cursor-pointer items-center gap-2 pb-2 text-small">
            <input type="checkbox" className="accent-pen" checked={hideNames}
                   onChange={(e) => setHideNames(e.target.checked)} />
            Скрыть ФИО учителей
          </label>
          <Button disabled={exporting !== null} onClick={() => download("pdf")}>
            {exporting === "pdf" ? "Готовлю PDF…" : "Скачать PDF"}
          </Button>
          <Button disabled={exporting !== null} onClick={() => download("xlsx")}>
            {exporting === "xlsx" ? "Готовлю Excel…" : "Скачать Excel"}
          </Button>
          <Button variant="primary" onClick={() => window.print()}>Распечатать</Button>
        </div>
      </div>

      {error && <p role="alert" className="mb-6 text-no print:hidden">{error}</p>}

      <div className="space-y-8 print:space-y-0">
        {sheets.map((sheet) => (
          <Sheet key={sheet.key} dir={dir} title={sheet.title} lessons={sheet.lessons} by={by}
                 surname={surname} />
        ))}
      </div>
    </div>
  );
}

function Sheet({ dir, title, lessons, by, surname }: {
  dir: Directory; title: string; lessons: LessonDTO[]; by: By; surname: (tid: string) => string;
}) {
  const cell = (day: number, period: number) => {
    const here = lessons.filter((l) => l.day === day && l.period === period);
    // Подгруппы одного предмета — одной записью, учителя через косую.
    const bySubject = new Map<string, LessonDTO[]>();
    for (const l of here) bySubject.set(l.subject_id, [...(bySubject.get(l.subject_id) ?? []), l]);
    return [...bySubject.values()];
  };
  const rooms = (items: LessonDTO[]) => [...new Set(items.map((l) => l.room_id).filter(Boolean))].join(", ");

  return (
    <section className="break-inside-avoid rounded-lg border border-rule bg-sheet p-6 print:break-after-page print:rounded-none print:border-0 print:p-0">
      <div className="flex items-baseline justify-between gap-4 border-b-2 border-ink pb-2">
        <h2 className="text-title">{title}</h2>
        <p className="text-small text-pencil">{dir.name}</p>
      </div>
      <table className="mt-3 w-full table-fixed border-collapse text-small">
        <thead>
          <tr>
            <th className="w-8" />
            {dir.days.map((d) => (
              <th key={d.n} className="border-b border-ink/30 px-2 py-1.5 text-left font-semibold">{d.name}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: dir.periods }, (_, p) => p + 1).map((period) => (
            <tr key={period} className="align-top">
              <th className="border-b border-rule py-1.5 pr-2 text-left font-normal text-pencil">{period}</th>
              {dir.days.map((d) => (
                <td key={d.n} className="h-12 border-b border-l border-rule px-2 py-1.5">
                  {cell(d.n, period).map((items) => {
                    const first = items[0];
                    const group = dir.groups[first.group_id];
                    const subject = dir.subjects[first.subject_id] ?? first.subject_id;
                    const room = rooms(items);
                    return (
                      <div key={first.subject_id} className="leading-tight">
                        <div className={cx("font-medium", by === "teacher" && "font-semibold")}>
                          {by === "teacher"
                            ? `${group?.class_ids.join(", ")}${group?.part ? ` (${group.part})` : ""}`
                            : subject}
                        </div>
                        <div className="text-[11px] text-pencil">
                          {by === "teacher" ? subject : items.map((l) => surname(l.teacher_id)).join(" / ")}
                          {room ? `, каб. ${room}` : ""}
                        </div>
                      </div>
                    );
                  })}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
