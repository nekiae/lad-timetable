import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api, type Directory, type LessonDTO, type Schedule } from "../api";

// Короткие названия для клетки сетки: полное «Физическая культура и здоровье»
// в клетку шириной в класс не помещается. Полное — в подсказке.
const SHORT: Record<string, string> = {
  "Белорусский язык": "Бел. яз.",
  "Белорусская литература": "Бел. лит.",
  "Русский язык": "Рус. яз.",
  "Русская литература": "Рус. лит.",
  "Иностранный язык": "Ин. яз.",
  "Математика": "Матем.",
  "Алгебра": "Алгебра",
  "Геометрия": "Геометр.",
  "Информатика": "Информ.",
  "Всемирная история": "Всем. ист.",
  "История Беларуси": "Ист. Бел.",
  "Обществоведение": "Общество",
  "География": "Геогр.",
  "Биология": "Биол.",
  "Физика": "Физика",
  "Химия": "Химия",
  "Астрономия": "Астрон.",
  "Физическая культура и здоровье": "Физ-ра",
  "Трудовое обучение": "Труд",
  "Изобразительное искусство": "ИЗО",
  "Музыка": "Музыка",
  "Черчение": "Черчение",
  "Допризывная и медицинская подготовка": "ДМП",
  "Искусство (отечественная и мировая художественная культура)": "Искусство",
};

function short(name: string) {
  return SHORT[name] ?? (name.length > 10 ? name.split(" ")[0].slice(0, 9) + "." : name);
}

function surname(full: string) {
  return full.split(" ")[0];
}

type Cell = LessonDTO[];

function buildGrid(dir: Directory, lessons: LessonDTO[]) {
  const grid = new Map<string, Cell>();
  for (const lesson of lessons) {
    for (const classId of dir.groups[lesson.group_id]?.class_ids ?? []) {
      const key = `${classId}|${lesson.day}|${lesson.period}`;
      grid.set(key, [...(grid.get(key) ?? []), lesson]);
    }
  }
  return grid;
}

// Сетка расписания: дни и уроки по вертикали, классы по горизонтали —
// так расписание висит на доске в учительской, и завуч читает его привычно.
export function SchedulePage() {
  const { id = "" } = useParams();
  const [schedule, setSchedule] = useState<Schedule | null>();
  const [hideNames, setHideNames] = useState(false);

  useEffect(() => {
    api.latest(id).then(setSchedule).catch(() => setSchedule(null));
  }, [id]);

  const grid = useMemo(
    () => (schedule ? buildGrid(schedule.directory, schedule.lessons) : new Map()),
    [schedule],
  );

  if (schedule === undefined) return <p className="p-10 text-pencil">Загружаю расписание…</p>;
  if (schedule === null)
    return (
      <div className="p-10">
        <p className="text-lg">Расписание ещё не составлено.</p>
        <Link to={`/s/${id}`} className="btn-primary mt-4">Перейти к составлению</Link>
      </div>
    );

  const { directory: dir, report, meta } = schedule;
  const teacherIndex = new Map(Object.keys(dir.teachers).map((t, i) => [t, i + 1]));
  const teacherName = (t: string) => (hideNames ? `Учитель ${teacherIndex.get(t)}` : surname(dir.teachers[t] ?? t));
  const seconds = meta.seconds ?? 0;

  return (
    <div className="px-4 py-8 md:px-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Расписание</h1>
          {report && (
            <p className="mt-2 max-w-3xl text-lg">
              Составлено за {seconds >= 90 ? `${Math.round(seconds / 60)} мин` : `${Math.round(seconds)} с`}.{" "}
              <span className={report.norm_violations ? "font-semibold text-red-pen" : ""}>
                {report.norm_violations === 0
                  ? "Санитарные нормы соблюдены полностью."
                  : `Нарушений санитарных норм: ${report.norm_violations}.`}
              </span>{" "}
              Окон у учителей за неделю: {report.teacher_gaps}. У классов окон нет.
            </p>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <label className="flex cursor-pointer items-center gap-2 text-sm">
            <input type="checkbox" checked={hideNames} onChange={(e) => setHideNames(e.target.checked)} />
            Скрыть ФИО учителей
          </label>
          <button className="btn-quiet" onClick={() => api.exportXlsx(id, schedule.lessons, hideNames)}>
            Скачать Excel
          </button>
        </div>
      </header>

      {schedule.stale && (
        <p className="mt-4 rounded-md border border-warn/30 bg-warn-soft px-4 py-2 text-sm">
          Данные школы изменились после составления. Сетка ниже — по прежним данным.
        </p>
      )}

      {report && report.violations.length > 0 && (
        <details className="mt-4 rounded-md border border-red-pen/30 bg-white px-4 py-2">
          <summary className="cursor-pointer font-medium text-red-pen">
            Что нарушено ({report.violations.length})
          </summary>
          <ul className="mt-2 space-y-1 text-sm">
            {report.violations.map((v, i) => (
              <li key={i}><b>{v.rule}</b> — {v.what}, {v.where}</li>
            ))}
          </ul>
        </details>
      )}

      <div className="mt-6 overflow-auto rounded-lg border border-rule bg-white" style={{ maxHeight: "calc(100vh - 220px)" }}>
        <table className="border-separate border-spacing-0 text-[13px] leading-tight">
          <thead>
            <tr>
              <th className="sticky left-0 top-0 z-30 border-b border-r border-rule bg-paper px-2 py-2" />
              {dir.classes.map((c) => (
                <th key={c.id} className="sticky top-0 z-20 min-w-[92px] border-b border-r border-rule bg-paper px-2 py-2 text-left font-semibold">
                  {c.name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {dir.days.map((day) =>
              Array.from({ length: dir.periods }, (_, p) => p + 1).map((period) => (
                <tr key={`${day.n}-${period}`}>
                  <th className={`sticky left-0 z-10 whitespace-nowrap border-r border-rule bg-paper px-2 text-left font-normal ${
                    period === 1 ? "border-t-2 border-t-ink/25" : "border-t border-t-rule"}`}>
                    {period === 1 && <span className="mr-2 font-semibold">{day.name.slice(0, 2)}</span>}
                    <span className="text-pencil">{period}</span>
                  </th>
                  {dir.classes.map((c) => {
                    const cell: Cell = grid.get(`${c.id}|${day.n}|${period}`) ?? [];
                    return (
                      <td key={c.id} className={`h-11 border-r border-rule px-1.5 align-top ${
                        period === 1 ? "border-t-2 border-t-ink/25" : "border-t border-t-rule"}`}>
                        {cell.map((l, i) => {
                          const part = dir.groups[l.group_id]?.part;
                          const subject = dir.subjects[l.subject_id] ?? l.subject_id;
                          return (
                            <div key={i} className="py-0.5"
                                 title={`${subject}${part ? `, ${part} гр.` : ""}\n${dir.teachers[l.teacher_id] ?? ""}${l.room_id ? `\nкаб. ${l.room_id}` : ""}`}>
                              <div className="font-medium">{short(subject)}{part ? ` (${part})` : ""}</div>
                              <div className="text-[11px] text-pencil">{teacherName(l.teacher_id)}</div>
                            </div>
                          );
                        })}
                      </td>
                    );
                  })}
                </tr>
              )),
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
