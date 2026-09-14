import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api, type Directory, type LessonDTO, type Report, type Schedule, type Verdict } from "../api";

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

// Клетка хранит номера уроков в массиве сетки — по номеру сервер понимает,
// какой урок двигать.
function buildGrid(dir: Directory, lessons: LessonDTO[]) {
  const grid = new Map<string, number[]>();
  lessons.forEach((lesson, index) => {
    for (const classId of dir.groups[lesson.group_id]?.class_ids ?? []) {
      const key = `${classId}|${lesson.day}|${lesson.period}`;
      grid.set(key, [...(grid.get(key) ?? []), index]);
    }
  });
  return grid;
}

const TINT: Record<Verdict["level"], string> = {
  ok: "bg-ok-soft",
  worse: "bg-warn-soft",
  no: "bg-red-soft/60",
};

type Snapshot = { lessons: LessonDTO[]; report: Report | null };

// Сетка расписания: дни и уроки по вертикали, классы по горизонтали —
// так расписание висит на доске в учительской, и завуч читает его привычно.
//
// Правка — щелчками, а не перетаскиванием: щёлкнул урок, неделя класса
// подсветилась (зелёное — можно, жёлтое — можно, но хуже, красное — нельзя),
// навёл на клетку — справа сказано, что будет, щёлкнул — уроки поменялись
// местами. Щелчки одинаково работают мышью и пальцем на планшете.
export function SchedulePage() {
  const { id = "" } = useParams();
  const [schedule, setSchedule] = useState<Schedule | null>();
  const [lessons, setLessons] = useState<LessonDTO[]>([]);
  const [report, setReport] = useState<Report | null>(null);
  const [history, setHistory] = useState<Snapshot[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [heat, setHeat] = useState<Record<string, Verdict> | null>(null);
  const [preview, setPreview] = useState<{ key: string; verdict: Verdict } | null>(null);
  const [last, setLast] = useState<Verdict | null>(null);
  const [hideNames, setHideNames] = useState(false);
  const [saved, setSaved] = useState<"idle" | "saving" | "saved">("idle");

  useEffect(() => {
    api.latest(id)
      .then((s) => {
        setSchedule(s);
        setLessons(s.lessons);
        setReport(s.report);
      })
      .catch(() => setSchedule(null));
  }, [id]);

  const dir = schedule?.directory;
  const grid = useMemo(() => (dir ? buildGrid(dir, lessons) : new Map<string, number[]>()), [dir, lessons]);

  if (schedule === undefined) return <p className="p-10 text-pencil">Загружаю расписание…</p>;
  if (schedule === null || !dir)
    return (
      <div className="p-10">
        <p className="text-lg">Расписание ещё не составлено.</p>
        <Link to={`/s/${id}`} className="btn-primary mt-4">Перейти к составлению</Link>
      </div>
    );

  const teacherIndex = new Map(Object.keys(dir.teachers).map((t, i) => [t, i + 1]));
  const teacherName = (t: string) =>
    hideNames ? `Учитель ${teacherIndex.get(t)}` : surname(dir.teachers[t] ?? t);
  const selectedClasses = new Set(
    selected !== null ? dir.groups[lessons[selected].group_id]?.class_ids ?? [] : []);
  const seconds = schedule.meta.seconds ?? 0;

  async function pick(index: number) {
    if (selected === index) {
      setSelected(null);
      setHeat(null);
      return;
    }
    setSelected(index);
    setHeat(null);
    setPreview(null);
    setHeat(await api.heatmap(id, lessons, index));
  }

  async function place(day: number, period: number) {
    if (selected === null || !heat) return;
    const verdict = heat[`${day}-${period}`];
    if (!verdict || verdict.level === "no") {
      setLast(verdict ?? null);
      return;
    }
    const result = await api.move(id, lessons, selected, day, period);
    setHistory((h) => [...h, { lessons, report }]);
    setLessons(result.lessons);
    setReport(result.report);
    setLast(result.verdict);
    setSelected(null);
    setHeat(null);
    setPreview(null);
    setSaved("idle");
  }

  function undo() {
    const previous = history.at(-1);
    if (!previous) return;
    setHistory((h) => h.slice(0, -1));
    setLessons(previous.lessons);
    setReport(previous.report);
    setLast(null);
    setSelected(null);
    setHeat(null);
    setSaved("idle");
  }

  async function save() {
    setSaved("saving");
    await api.saveEdited(id, lessons);
    setHistory([]);
    setSaved("saved");
  }

  const shown = preview?.verdict ?? last;

  return (
    <div className="px-4 py-8 md:px-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Расписание</h1>
          {report && (
            <p className="mt-2 max-w-3xl text-lg">
              {schedule.meta.status !== "EDITED" && history.length === 0 && (
                <>Составлено за {seconds >= 90 ? `${Math.round(seconds / 60)} мин` : `${Math.round(seconds)} с`}. </>
              )}
              <span className={report.norm_violations ? "font-semibold text-red-pen" : ""}>
                {report.norm_violations === 0
                  ? "Санитарные нормы соблюдены полностью."
                  : `Нарушений санитарных норм: ${report.norm_violations}.`}
              </span>{" "}
              Окон у учителей за неделю: {report.teacher_gaps}.{" "}
              {report.structural_violations > 0
                ? <span className="font-semibold text-red-pen">Конфликтов в сетке: {report.structural_violations}.</span>
                : "Конфликтов нет."}
            </p>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <label className="flex cursor-pointer items-center gap-2 text-sm">
            <input type="checkbox" checked={hideNames} onChange={(e) => setHideNames(e.target.checked)} />
            Скрыть ФИО учителей
          </label>
          <button className="btn-quiet" disabled={!history.length} onClick={undo}>
            Отменить ход
          </button>
          <button className="btn-quiet" disabled={!history.length || saved === "saving"} onClick={save}>
            {saved === "saved" ? "Версия сохранена" : "Сохранить версию"}
          </button>
          <button className="btn-quiet" onClick={() => api.exportXlsx(id, lessons, hideNames)}>
            Скачать Excel
          </button>
        </div>
      </header>

      {schedule.stale && (
        <p className="mt-4 rounded-md border border-warn/30 bg-warn-soft px-4 py-2 text-sm">
          Данные школы изменились после составления. Сетка ниже — по прежним данным.
        </p>
      )}

      <div className="mt-6 flex gap-6 max-lg:flex-col">
        <div className="min-w-0 flex-1 overflow-auto rounded-lg border border-rule bg-white"
             style={{ maxHeight: "calc(100vh - 200px)" }}>
          <table className="border-separate border-spacing-0 text-[13px] leading-tight">
            <thead>
              <tr>
                <th className="sticky left-0 top-0 z-30 border-b border-r border-rule bg-paper px-2 py-2" />
                {dir.classes.map((c) => (
                  <th key={c.id}
                      className={`sticky top-0 z-20 min-w-[92px] border-b border-r border-rule px-2 py-2 text-left font-semibold ${
                        selectedClasses.has(c.id) ? "bg-pen-soft text-pen" : "bg-paper"}`}>
                    {c.name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {dir.days.map((day) =>
                Array.from({ length: dir.periods }, (_, p) => p + 1).map((period) => {
                  const key = `${day.n}-${period}`;
                  const verdict = heat?.[key];
                  return (
                    <tr key={key}>
                      <th className={`sticky left-0 z-10 whitespace-nowrap border-r border-rule bg-paper px-2 text-left font-normal ${
                        period === 1 ? "border-t-2 border-t-ink/25" : "border-t border-t-rule"}`}>
                        {period === 1 && <span className="mr-2 font-semibold">{day.name.slice(0, 2)}</span>}
                        <span className="text-pencil">{period}</span>
                      </th>
                      {dir.classes.map((c) => {
                        const cell = grid.get(`${c.id}|${day.n}|${period}`) ?? [];
                        const target = selectedClasses.has(c.id) && verdict;
                        const isSource = selected !== null && cell.includes(selected);
                        return (
                          <td key={c.id}
                              onMouseEnter={() => target && setPreview({ key, verdict })}
                              onMouseLeave={() => target && setPreview(null)}
                              onClick={() => {
                                if (target && !isSource) place(day.n, period);
                                else if (cell.length) pick(cell[0]);
                              }}
                              className={`h-11 cursor-pointer border-r border-rule px-1.5 align-top ${
                                period === 1 ? "border-t-2 border-t-ink/25" : "border-t border-t-rule"} ${
                                isSource ? "outline outline-2 -outline-offset-2 outline-pen" : ""} ${
                                target ? TINT[verdict.level] : "hover:bg-paper"}`}>
                            {cell.map((i) => {
                              const l = lessons[i];
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
                  );
                }),
              )}
            </tbody>
          </table>
        </div>

        <aside className="w-full shrink-0 lg:w-80" aria-live="polite">
          {selected === null && !shown && (
            <div className="rounded-lg border border-rule bg-white p-4 text-sm leading-relaxed">
              <p className="font-medium">Как поправить руками</p>
              <p className="mt-2 text-ink/80">
                Щёлкните урок. Клетки его класса подсветятся: зелёные — можно поставить,
                жёлтые — можно, но станет хуже, красные — нельзя. Щелчок по клетке меняет
                уроки местами.
              </p>
            </div>
          )}
          {selected !== null && !heat && (
            <p className="rounded-lg border border-rule bg-white p-4 text-sm text-pencil">Проверяю все клетки недели…</p>
          )}
          {/* Список не прячется при наведении: иначе наведение на пункт убирает
              сам пункт, и щелчок уходит в пустоту (найдено 14.09.2026). */}
          {selected !== null && heat && (
            <Options heat={heat} dir={dir} current={`${lessons[selected].day}-${lessons[selected].period}`}
                     onPick={(day, period) => place(day, period)}
                     onHover={(key) => setPreview(key ? { key, verdict: heat[key] } : null)} />
          )}
          {shown && <VerdictCard verdict={shown} applied={!preview && last === shown} />}
          {report && report.violations.length > 0 && (
            <details className="mt-4 rounded-lg border border-red-pen/30 bg-white p-4 text-sm">
              <summary className="cursor-pointer font-medium text-red-pen">
                Что нарушено в сетке ({report.violations.length})
              </summary>
              <ul className="mt-2 space-y-1">
                {report.violations.map((v, i) => <li key={i}>{v.what}, {v.where}</li>)}
              </ul>
            </details>
          )}
        </aside>
      </div>
    </div>
  );
}

// Куда можно поставить — списком. На плотной сетке годных клеток обычно
// три-пять из сорока, и искать их прокруткой по подсветке утомительно.
// Сначала те, что улучшают сетку, потом нейтральные, потом «хуже».
function Options({ heat, dir, current, onPick, onHover }: {
  heat: Record<string, Verdict>;
  dir: Directory;
  current: string;
  onPick: (day: number, period: number) => void;
  onHover: (key: string | null) => void;
}) {
  const rank = (v: Verdict) => (v.level === "ok" ? (v.gains.length ? 0 : 1) : 2);
  const options = Object.entries(heat)
    .filter(([key, v]) => key !== current && v.level !== "no")
    .sort(([, a], [, b]) => rank(a) - rank(b));
  const blocked = Object.values(heat).filter((v) => v.level === "no").length;
  const dayName = (n: number) => dir.days.find((d) => d.n === n)?.name ?? String(n);

  return (
    <div className="rounded-lg border border-rule bg-white p-4 text-sm">
      {options.length === 0 ? (
        <p>
          Этот урок некуда переставить без нарушений: все {blocked} клеток недели заняты
          запретами. Наведите на красную клетку, чтобы узнать, что мешает.
        </p>
      ) : (
        <>
          <p className="font-medium">Куда можно поставить</p>
          <ul className="mt-2 space-y-1">
            {options.map(([key, v]) => {
              const [day, period] = key.split("-").map(Number);
              // У жёлтого варианта первым — чем он хуже: ради этого завуч и смотрит.
              const note = (v.level === "worse" ? v.costs[0]?.text : v.gains[0]?.text)
                ?? "ничего не изменится";
              return (
                <li key={key}>
                  <button
                    className={`w-full rounded-md border px-3 py-2 text-left hover:border-pen ${
                      v.level === "ok" ? "border-ok/30 bg-ok-soft" : "border-warn/30 bg-warn-soft"}`}
                    onMouseEnter={() => onHover(key)} onMouseLeave={() => onHover(null)}
                    onFocus={() => onHover(key)} onBlur={() => onHover(null)}
                    onClick={() => onPick(day, period)}>
                    <span className="font-medium">{dayName(day)}, {period}-й урок</span>
                    <span className="block text-ink/70">{note}</span>
                  </button>
                </li>
              );
            })}
          </ul>
          <p className="mt-3 text-pencil">Ещё {blocked} клеток — нельзя. Наведите на красную, чтобы узнать почему.</p>
        </>
      )}
    </div>
  );
}

function VerdictCard({ verdict, applied }: { verdict: Verdict; applied: boolean }) {
  const title = applied
    ? "Уроки поменялись местами"
    : verdict.level === "no" ? "Сюда нельзя" : verdict.level === "worse" ? "Можно, но станет хуже" : "Можно";
  const tone = verdict.level === "no" ? "border-red-pen/40" : verdict.level === "worse" ? "border-warn/40" : "border-ok/40";
  return (
    <div className={`rounded-lg border-2 bg-white p-4 text-sm ${tone}`}>
      <p className={`font-semibold ${verdict.level === "no" ? "text-red-pen" : ""}`}>{title}</p>
      {verdict.blocking.length > 0 && (
        <ul className="mt-2 space-y-1.5">
          {verdict.blocking.map((r, i) => (
            <li key={i}>
              {r.text}
              {r.source && <span className="text-pencil"> — {r.source} № 525</span>}
            </li>
          ))}
        </ul>
      )}
      {verdict.costs.length > 0 && (
        <ul className="mt-2 space-y-1 text-warn">
          {verdict.costs.map((r, i) => <li key={i}>{r.text}</li>)}
        </ul>
      )}
      {verdict.gains.length > 0 && (
        <ul className="mt-2 space-y-1 text-ok">
          {verdict.gains.map((r, i) => <li key={i}>{r.text}</li>)}
        </ul>
      )}
      {verdict.level === "ok" && !verdict.costs.length && !verdict.gains.length && !applied && (
        <p className="mt-1 text-ink/70">Ничего не нарушится, метрики не изменятся.</p>
      )}
    </div>
  );
}
