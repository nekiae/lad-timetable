import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";

import { api, type Directory, type LessonDTO, type Progress, type Report, type Schedule, type Verdict } from "../api";
import { Button, ButtonLink, EmptyState, Notice, Panel, Reasons, cx } from "../ui";

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
  "Геометрия": "Геометрия",
  "Информатика": "Информ.",
  "Всемирная история": "Всем. ист.",
  "История Беларуси": "Ист. Бел.",
  "Обществоведение": "Общество",
  "География": "География",
  "Биология": "Биология",
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

// Уроки одной клетки, сгруппированные по предмету (подгруппы деления).
function bySubject(cell: number[], lessons: LessonDTO[]) {
  const groups = new Map<string, number[]>();
  for (const i of cell) groups.set(lessons[i].subject_id, [...(groups.get(lessons[i].subject_id) ?? []), i]);
  return [...groups.values()];
}

// Подсветка клеток при правке — единственное место, где интерфейс
// позволяет себе цвет крупно (docs/DESIGN.md §2.1).
const TINT: Record<Verdict["level"], string> = {
  ok: "bg-ok-soft",
  worse: "bg-worse-soft",
  no: "bg-no-soft/70",
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
  // Итог последней попытки хода: применён он или отклонён. Отказ в красную
  // клетку тоже показывается, но заголовком «Сюда нельзя», а не «поменялись».
  const [last, setLast] = useState<{ verdict: Verdict; applied: boolean;
                                     target?: { index: number; day: number; period: number } } | null>(null);
  const [hideNames, setHideNames] = useState(false);
  const [saved, setSaved] = useState<"idle" | "saving" | "saved">("idle");
  // Закреплённые уроки — ПОЗИЦИИ (урок + клетка), а не номера в массиве:
  // номера меняются после каждой пересборки, а закрепление должно пережить её.
  const [pins, setPins] = useState<LessonDTO[]>([]);
  const [settings, setSettings] = useState<Record<string, unknown>>({});
  const [rebuild, setRebuild] = useState<{ job: string; started: number; pinsCount: number;
                                           progress?: Progress; stopped?: boolean } | null>(null);
  const [rebuildResult, setRebuildResult] = useState<{ ok: boolean; text: string } | null>(null);
  const [flash, setFlash] = useState<Set<string>>(new Set());
  const [now, setNow] = useState(0);
  // Сетка «до» и где стояли её уроки на экране — чтобы после пересборки
  // перенести переставленные уроки анимацией из старых клеток в новые.
  const pendingAnimation = useRef<{ before: LessonDTO[]; rects: Map<string, DOMRect> } | null>(null);
  // Остановил ли пересборку человек — в ref, а не в состоянии: читается в конце
  // задачи, и отложенное обновление состояния React могло бы не успеть.
  const stoppedByUser = useRef(false);

  useEffect(() => {
    api.latest(id)
      .then((s) => {
        setSchedule(s);
        setLessons(s.lessons);
        setReport(s.report);
      })
      .catch(() => setSchedule(null));
    api.school(id).then((s) => setSettings(s.doc.settings)).catch(() => undefined);
  }, [id]);

  useEffect(() => {
    if (!rebuild) return;
    const timer = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(timer);
  }, [rebuild]);

  useLayoutEffect(() => {
    const pending = pendingAnimation.current;
    if (!pending || !schedule) return;
    pendingAnimation.current = null;
    animateMoves(pending.before, lessons, pending.rects, schedule.directory, setFlash);
  }, [lessons, schedule]);

  const dir = schedule?.directory;
  const grid = useMemo(() => (dir ? buildGrid(dir, lessons) : new Map<string, number[]>()), [dir, lessons]);

  if (schedule === undefined) return <p className="px-4 py-10 text-pencil md:px-8">Загружаю расписание…</p>;
  if (schedule === null || !dir)
    return (
      <EmptyState text="Расписание ещё не составлено."
                  action={<ButtonLink to={`/s/${id}`} variant="primary">Перейти к составлению</ButtonLink>} />
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
    setLast(null);
    setHeat(await api.heatmap(id, lessons, index));
  }

  async function place(day: number, period: number) {
    if (selected === null || !heat) return;
    const verdict = heat[`${day}-${period}`];
    if (!verdict || verdict.level === "no") {
      setLast(verdict ? { verdict, applied: false, target: { index: selected, day, period } } : null);
      return;
    }
    const result = await api.move(id, lessons, selected, day, period);
    setHistory((h) => [...h, { lessons, report }]);
    setLessons(result.lessons);
    setReport(result.report);
    setLast({ verdict: result.verdict, applied: true });
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

  const samePlace = (a: LessonDTO, b: LessonDTO) =>
    lessonKey(a) === lessonKey(b) && a.day === b.day && a.period === b.period;
  const isPinned = (l: LessonDTO) => pins.some((p) => samePlace(p, l));

  // Подгруппы одного деления закрепляются и переезжают вместе: они обязаны
  // стоять в одном часе (HARD-9), по отдельности их не поставить.
  function partners(index: number): number[] {
    const l = lessons[index];
    const group = dir!.groups[l.group_id];
    if (!group?.part) return [index];
    return lessons.flatMap((x, i) =>
      x.day === l.day && x.period === l.period && x.subject_id === l.subject_id
        && dir!.groups[x.group_id]?.class_ids.join() === group.class_ids.join() ? [i] : []);
  }

  function togglePin(index: number) {
    const group = partners(index).map((i) => lessons[i]);
    setPins((current) => (isPinned(lessons[index])
      ? current.filter((p) => !group.some((g) => samePlace(g, p)))
      : [...current, ...group]));
  }

  // «Поставить сюда и пересобрать остальное»: урок закрепляется в выбранной
  // клетке, прежнее закрепление этого урока снимается, остальное — солверу.
  function placeAndRebuild(index: number, day: number, period: number) {
    const moving = partners(index);
    const kept = pins.filter((p) => !moving.some((i) => samePlace(lessons[i], p)));
    const next = [...kept, ...moving.map((i) => ({ ...lessons[i], day, period, room_id: null }))];
    setPins(next);
    startRebuild(next);
  }

  async function startRebuild(nextPins: LessonDTO[]) {
    setSelected(null);
    setHeat(null);
    setPreview(null);
    setLast(null);
    setRebuildResult(null);
    const before = lessons;
    const beforeReport = report;
    const started = Date.now();
    try {
      const { job_id } = await api.solve(id, {
        budget: REBUILD_SECONDS,
        preset: typeof settings.preset === "string" ? settings.preset : "Поровну",
        rules: (settings.rules as Record<string, string>) ?? {},
        prefs: (settings.prefs as Record<string, number>) ?? {},
        pinned: nextPins,
        hint: lessons, // старт с текущей сетки — законная находится почти сразу
        keep: true, // беречь сетку: двигать нужное, а не перетасовывать всё ради удобства
      });
      stoppedByUser.current = false;
      setRebuild({ job: job_id, started, pinsCount: nextPins.length });
      api.watch(job_id, (p) => setRebuild((r) => (r ? { ...r, progress: p } : r)), async (done) => {
        const stopped = stoppedByUser.current;
        setRebuild(null);
        if (done.type !== "result" || !done.schedule_id) {
          setRebuildResult({
            ok: false,
            text: done.type === "problems" ? `В данных школы ошибки: ${done.problems?.[0] ?? ""}`
              : done.type === "error" ? "Пересборка остановилась с ошибкой."
                : stopped ? "Остановлено раньше, чем нашлась законная сетка."
                  : "Вокруг этих закреплённых уроков расписание не складывается: они противоречат нормам или друг другу. Открепите последний и попробуйте снова.",
          });
          return;
        }
        const fresh = await api.schedule(id, done.schedule_id);
        pendingAnimation.current = { before, rects: captureRects(dir!, before) };
        setHistory((h) => [...h, { lessons: before, report: beforeReport }]);
        setSchedule(fresh);
        setLessons(fresh.lessons);
        setReport(fresh.report);
        setSaved("saved");
        const moved = diffMoves(before, fresh.lessons).length;
        const gaps = beforeReport && fresh.report
          ? ` Окна у учителей: ${beforeReport.teacher_gaps} → ${fresh.report.teacher_gaps}.` : "";
        const norms = fresh.report
          ? (fresh.report.norm_violations ? ` Нарушений норм: ${fresh.report.norm_violations}.` : " Нормы соблюдены.") : "";
        setRebuildResult({
          ok: true,
          text: `Пересобрано за ${Math.round((Date.now() - started) / 1000)} с. Переставлено уроков: ${moved}.${gaps}${norms}`,
        });
      });
    } catch (e) {
      setRebuildResult({ ok: false, text: e instanceof Error ? e.message : String(e) });
    }
  }

  // Карточка справа: под курсором — превью наведённой клетки, но если курсор
  // стоит над той самой клеткой, куда только что щёлкнули и получили отказ, —
  // карточка отказа с кнопкой «Поставить сюда и пересобрать». Иначе превью
  // перекрывало её, и кнопка пропадала ровно тогда, когда нужна (найдено
  // сквозным прогоном 15.09.2026: после щелчка курсор остаётся на клетке).
  const lastKey = last?.target ? `${last.target.day}-${last.target.period}` : null;
  const shown = preview && preview.key !== lastKey ? { verdict: preview.verdict, applied: false } : last;
  const dayBorder = (period: number) => (period === 1 ? "border-t-2 border-t-ink/20" : "border-t border-t-rule");

  return (
    <div className="px-4 py-6 md:px-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-title">Расписание</h1>
          {report && (
            <p className="mt-1 max-w-4xl">
              {schedule.meta.status !== "EDITED" && history.length === 0 && (
                <span className="text-pencil">
                  Составлено за {seconds >= 90 ? `${Math.round(seconds / 60)} мин` : `${Math.round(seconds)} с`}.{" "}
                </span>
              )}
              <span className={report.norm_violations ? "font-semibold text-no" : ""}>
                {report.norm_violations === 0
                  ? "Санитарные нормы соблюдены полностью."
                  : `Нарушений санитарных норм: ${report.norm_violations}.`}
              </span>{" "}
              Окон у учителей за неделю: {report.teacher_gaps}.{" "}
              {report.structural_violations > 0
                ? <span className="font-semibold text-no">Конфликтов в сетке: {report.structural_violations}.</span>
                : "Конфликтов нет."}
            </p>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <label className="mr-2 flex cursor-pointer items-center gap-2 text-small">
            <input type="checkbox" className="accent-pen" checked={hideNames}
                   onChange={(e) => setHideNames(e.target.checked)} />
            Скрыть ФИО учителей
          </label>
          <Button disabled={!history.length} onClick={undo}>Отменить ход</Button>
          <Button variant={history.length ? "primary" : "quiet"}
                  disabled={!history.length || saved === "saving"} onClick={save}>
            {saved === "saved" ? "Версия сохранена" : "Сохранить версию"}
          </Button>
          <Button onClick={() => api.exportXlsx(id, lessons, hideNames)}>Скачать Excel</Button>
          {/* Печать берёт сохранённую версию — несохранённые ходы на бумагу не попадут. */}
          {history.length === 0 && <ButtonLink to={`/s/${id}/print`}>Печать</ButtonLink>}
        </div>
      </header>

      {/* Нормы, которые в этих данных выполнить физически нельзя (у 11А 4 часа
          физкультуры — без соседних дней их не расставить). Солвер ослабляет их
          только для этого класса и говорит, что поменять во вводе. Без этой плашки
          завуч видит «нарушений: 2» и не знает, что это не сбой и как это исправить. */}
      {schedule.meta.relaxed && schedule.meta.relaxed.length > 0 && history.length === 0 && (
        <Notice tone="worse" className="mt-4" title="Нормы, которые в ваших данных выполнить нельзя">
          <ul className="list-disc space-y-1 pl-5">
            {schedule.meta.relaxed.map((line) => <li key={line}>{line}</li>)}
          </ul>
        </Notice>
      )}

      {schedule.stale && (
        <Notice tone="worse" className="mt-4">
          Данные школы изменились после составления. Сетка ниже — по прежним данным.
        </Notice>
      )}

      <div className="mt-5 flex gap-6 max-lg:flex-col">
        <div data-grid className={cx("min-w-0 flex-1 overflow-auto rounded-lg border border-rule bg-sheet transition-opacity duration-300",
                           rebuild && "pointer-events-none opacity-60")}
             style={{ maxHeight: "calc(100vh - 180px)" }}>
          <table className="border-separate border-spacing-0 font-narrow text-cell">
            <thead>
              <tr>
                <th className="sticky left-0 top-0 z-30 border-b border-r border-rule bg-paper" />
                {dir.classes.map((c) => (
                  <th key={c.id} scope="col"
                      className={cx(
                        "sticky top-0 z-20 min-w-[88px] border-b border-r border-rule px-2 py-2 text-left text-small font-semibold",
                        selectedClasses.has(c.id) ? "bg-pen-soft text-pen" : "bg-paper")}>
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
                      <th scope="row"
                          className={cx("sticky left-0 z-10 w-12 whitespace-nowrap border-r border-rule bg-paper px-2 text-left font-normal",
                                        dayBorder(period))}>
                        {period === 1 && <span className="mr-1.5 font-semibold">{day.name.slice(0, 2)}</span>}
                        <span className="text-pencil">{period}</span>
                      </th>
                      {dir.classes.map((c) => {
                        const cell = grid.get(`${c.id}|${day.n}|${period}`) ?? [];
                        const target = selectedClasses.has(c.id) && verdict;
                        const isSource = selected !== null && cell.includes(selected);
                        return (
                          <td key={c.id} data-cell={cellKey(c.id, day.n, period)}
                              onMouseEnter={() => target && setPreview({ key, verdict })}
                              onMouseLeave={() => target && setPreview(null)}
                              onClick={() => {
                                if (target && !isSource) place(day.n, period);
                                else if (cell.length) pick(cell[0]);
                              }}
                              className={cx(
                                "h-11 cursor-pointer border-r border-rule px-1.5 align-top",
                                dayBorder(period),
                                isSource && "outline outline-2 -outline-offset-2 outline-pen",
                                flash.has(cellKey(c.id, day.n, period)) && "cell-flash",
                                target ? TINT[verdict.level] : "hover:bg-paper")}>
                            {bySubject(cell, lessons).map((same) => {
                              const l = lessons[same[0]];
                              const subject = dir.subjects[l.subject_id] ?? l.subject_id;
                              // Подгруппы одного предмета — одной записью: предмет один раз,
                              // учителя через косую. Иначе каждая клетка с делением
                              // занимает четыре строки и растягивает весь ряд недели.
                              const part = same.length === 1 ? dir.groups[l.group_id]?.part : null;
                              const title = same.map((i) => {
                                const x = lessons[i];
                                const p = dir.groups[x.group_id]?.part;
                                return `${subject}${p ? `, ${p} гр.` : ""}\n${dir.teachers[x.teacher_id] ?? ""}${x.room_id ? `\nкаб. ${x.room_id}` : ""}`;
                              }).join("\n\n");
                              return (
                                <div key={same[0]} title={isPinned(l) ? `${title}\n\nЗакреплён` : title}
                                     className={cx("py-0.5", isPinned(l) && "-ml-1.5 border-l-[3px] border-pen pl-1")}>
                                  <div className="font-medium">{short(subject)}{part ? ` (${part})` : ""}</div>
                                  <div className="text-pencil">{same.map((i) => teacherName(lessons[i].teacher_id)).join(" / ")}</div>
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

        {/* Поля: здесь объяснения, как замечания учителя на полях тетради. */}
        <aside className="w-full shrink-0 space-y-4 lg:w-80" aria-live="polite">
          {rebuild && (
            <RebuildProgress rebuild={rebuild} now={now}
                             onStop={() => {
                               stoppedByUser.current = true;
                               setRebuild((r) => (r ? { ...r, stopped: true } : r));
                               api.stop(rebuild.job);
                             }} />
          )}
          {rebuildResult && !rebuild && (
            <Notice tone={rebuildResult.ok ? "ok" : "no"} title={rebuildResult.ok ? "Пересобрано" : "Не получилось пересобрать"}>
              {rebuildResult.text}
            </Notice>
          )}
          {selected !== null && !rebuild && (
            <Panel as="div" className="flex items-center justify-between gap-3 text-small">
              <span className="min-w-0">
                <span className="block font-medium">
                  {dir.subjects[lessons[selected].subject_id]}, {dir.groups[lessons[selected].group_id]?.class_ids.join(", ")}
                </span>
                <span className="block text-pencil">
                  {dir.days.find((d) => d.n === lessons[selected].day)?.name}, {lessons[selected].period}-й урок
                </span>
              </span>
              <Button onClick={() => togglePin(selected)}>
                {isPinned(lessons[selected]) ? "Открепить" : "Закрепить"}
              </Button>
            </Panel>
          )}
          {pins.length > 0 && !rebuild && (
            <Panel as="div" className="text-small">
              <p className="text-heading">Закреплено уроков: {pins.length}</p>
              <p className="mt-1 text-pencil">Пересборка оставит их на местах и переставит остальное по нормам.</p>
              <ul className="mt-2 max-h-40 space-y-1 overflow-auto">
                {pins.map((p, n) => (
                  <li key={`${lessonKey(p)}-${p.day}-${p.period}`} className="flex items-baseline justify-between gap-2">
                    <span className="min-w-0 truncate">
                      {dir.groups[p.group_id]?.class_ids.join(", ")} {short(dir.subjects[p.subject_id] ?? "")},{" "}
                      {dir.days.find((d) => d.n === p.day)?.name.slice(0, 2)} {p.period}-й
                    </span>
                    <button type="button" className="shrink-0 text-pen underline-offset-4 hover:underline"
                            onClick={() => setPins((all) => all.filter((_, i) => i !== n))}>
                      открепить
                    </button>
                  </li>
                ))}
              </ul>
              <div className="mt-3 flex flex-wrap gap-2">
                <Button variant="primary" onClick={() => startRebuild(pins)}>Пересобрать вокруг закреплённых</Button>
                <Button onClick={() => setPins([])}>Открепить все</Button>
              </div>
            </Panel>
          )}
          {selected === null && !shown && !rebuild && pins.length === 0 && (
            <Panel as="div" className="text-small">
              <p className="text-heading">Как поправить руками</p>
              <p className="mt-2 text-ink/80">
                Щёлкните урок. Клетки его класса подсветятся: зелёные — можно поставить,
                жёлтые — можно, но станет хуже, красные — нельзя. Щелчок по клетке меняет
                уроки местами. Урок можно закрепить — и пересобрать всё остальное вокруг
                закреплённых.
              </p>
            </Panel>
          )}
          {selected !== null && !heat && (
            <Panel as="div" className="text-small text-pencil">Проверяю все клетки недели…</Panel>
          )}
          {/* Список не прячется при наведении: иначе наведение на пункт убирает
              сам пункт, и щелчок уходит в пустоту (найдено 14.09.2026). */}
          {selected !== null && heat && (
            <Options heat={heat} dir={dir} lessons={lessons} current={`${lessons[selected].day}-${lessons[selected].period}`}
                     onPick={(day, period) => place(day, period)}
                     onHover={(key) => setPreview(key ? { key, verdict: heat[key] } : null)} />
          )}
          {shown && !rebuild && (
            <VerdictCard verdict={shown.verdict} applied={shown.applied}
                         onRebuild={"target" in shown && shown.target
                           ? () => placeAndRebuild(shown.target!.index, shown.target!.day, shown.target!.period)
                           : undefined} />
          )}
          {report && report.violations.length > 0 && (
            <details className="rounded-lg border border-no/30 bg-sheet p-4 text-small">
              <summary className="cursor-pointer font-semibold text-no">
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
function Options({ heat, dir, lessons, current, onPick, onHover }: {
  heat: Record<string, Verdict>;
  dir: Directory;
  lessons: LessonDTO[];
  current: string;
  onPick: (day: number, period: number) => void;
  onHover: (key: string | null) => void;
}) {
  const rank = (v: Verdict) => (v.level === "ok" ? (v.gains.length ? 0 : 1) : 2);
  // Обмен с таким же уроком (та же физкультура у того же учителя) формально
  // «можно», но сетка не меняется — в списке он только сбивает с толку.
  const same = (a: LessonDTO, b: LessonDTO) =>
    a.group_id === b.group_id && a.subject_id === b.subject_id && a.teacher_id === b.teacher_id;
  const noop = (v: Verdict) =>
    v.swapped.length > 0 && v.swapped.every((i) => v.moved.some((m) => same(lessons[m], lessons[i])));
  const options = Object.entries(heat)
    .filter(([key, v]) => key !== current && v.level !== "no" && !noop(v))
    .sort(([, a], [, b]) => rank(a) - rank(b));
  const blocked = Object.values(heat).filter((v) => v.level === "no").length;
  const dayName = (n: number) => dir.days.find((d) => d.n === n)?.name ?? String(n);

  return (
    <Panel as="div" className="text-small">
      {options.length === 0 ? (
        <p>
          Этот урок некуда переставить без нарушений: все {blocked} клеток недели заняты
          запретами. Наведите на красную клетку, чтобы узнать, что мешает.
        </p>
      ) : (
        <>
          <p className="text-heading">Куда можно поставить</p>
          <ul className="mt-2 space-y-1.5">
            {options.map(([key, v]) => {
              const [day, period] = key.split("-").map(Number);
              // У жёлтого варианта первым — чем он хуже: ради этого завуч и смотрит.
              const note = (v.level === "worse" ? v.costs[0]?.text : v.gains[0]?.text)
                ?? "ничего не изменится";
              return (
                <li key={key}>
                  <button
                    type="button"
                    className={cx(
                      "w-full rounded border px-3 py-2 text-left transition-colors duration-150 hover:border-pen",
                      v.level === "ok" ? "border-ok/30 bg-ok-soft" : "border-worse/30 bg-worse-soft")}
                    onMouseEnter={() => onHover(key)} onMouseLeave={() => onHover(null)}
                    onFocus={() => onHover(key)} onBlur={() => onHover(null)}
                    onClick={() => onPick(day, period)}>
                    <span className="font-medium">{dayName(day)}, {period}-й урок</span>
                    <span className="block text-ink/75">{note}</span>
                  </button>
                </li>
              );
            })}
          </ul>
          <p className="mt-3 text-pencil">Ещё {blocked} клеток — нельзя. Наведите на красную, чтобы узнать почему.</p>
        </>
      )}
    </Panel>
  );
}

function VerdictCard({ verdict, applied, onRebuild }: { verdict: Verdict; applied: boolean; onRebuild?: () => void }) {
  const title = applied
    ? "Уроки поменялись местами"
    : verdict.level === "no" ? "Сюда нельзя" : verdict.level === "worse" ? "Можно, но станет хуже" : "Можно";
  const tone = verdict.level === "no" ? "border-no/50" : verdict.level === "worse" ? "border-worse/40" : "border-ok/40";
  return (
    <div className={cx("rounded-lg border-2 bg-sheet p-4 text-small", tone)}>
      <p className={cx("text-heading", verdict.level === "no" && "text-no")}>{title}</p>
      <Reasons tone="no" items={verdict.blocking.map((r) => ({
        text: r.text, source: r.source ? `${r.source} № 525` : null }))} />
      <Reasons tone="worse" items={verdict.costs} />
      <Reasons tone="ok" items={verdict.gains} />
      {verdict.level === "ok" && !verdict.costs.length && !verdict.gains.length && !applied && (
        <p className="mt-1 text-pencil">Ничего не нарушится, метрики не изменятся.</p>
      )}
      {/* Обменом нельзя — но можно поставить урок сюда силой, а остальное пусть
          переставит солвер, так, чтобы нормы снова сошлись. */}
      {onRebuild && (
        <div className="mt-3 border-t border-rule pt-3">
          <Button variant="primary" onClick={onRebuild}>Поставить сюда и пересобрать остальное</Button>
          <p className="mt-1.5 text-pencil">Урок закрепится здесь, остальное система переставит по нормам.</p>
        </div>
      )}
    </div>
  );
}

const REBUILD_SECONDS = 40;

const lessonKey = (l: LessonDTO) => `${l.group_id}|${l.subject_id}|${l.teacher_id}`;
const cellKey = (classId: string, day: number, period: number) => `${classId}|${day}|${period}`;

// Какие уроки куда переехали. Уроки одной строки нагрузки взаимозаменяемы:
// те, что остались в своих клетках, не считаются, оставшиеся «откуда» и «куда»
// сопоставляются по порядку.
function diffMoves(before: LessonDTO[], after: LessonDTO[]) {
  const places = (list: LessonDTO[]) => {
    const map = new Map<string, string[]>();
    for (const l of list) map.set(lessonKey(l), [...(map.get(lessonKey(l)) ?? []), `${l.day}|${l.period}`]);
    return map;
  };
  const was = places(before), now = places(after);
  const moves: { key: string; from: string; to: string }[] = [];
  for (const [key, olds] of was) {
    const fresh = [...(now.get(key) ?? [])];
    const left = olds.filter((place) => {
      const at = fresh.indexOf(place);
      if (at < 0) return true;
      fresh.splice(at, 1);
      return false;
    });
    left.forEach((from, i) => fresh[i] && moves.push({ key, from, to: fresh[i] }));
  }
  return moves;
}

function captureRects(dir: Directory, list: LessonDTO[]) {
  const rects = new Map<string, DOMRect>();
  for (const l of list) {
    const classId = dir.groups[l.group_id]?.class_ids[0];
    const cell = classId && document.querySelector(`[data-cell="${cellKey(classId, l.day, l.period)}"]`);
    if (cell) rects.set(`${lessonKey(l)}|${l.day}|${l.period}`, cell.getBoundingClientRect());
  }
  return rects;
}

// Перелёт переставленных уроков из старых клеток в новые — синие плашки
// с названием предмета, по очереди, затем вспышка клеток, куда они сели.
// Движение отвечает на действие человека и показывает, что изменилось
// (docs/DESIGN.md §5). При prefers-reduced-motion — только вспышка.
function animateMoves(before: LessonDTO[], after: LessonDTO[], rects: Map<string, DOMRect>,
                      dir: Directory, setFlash: (cells: Set<string>) => void) {
  const moves = diffMoves(before, after);
  if (!moves.length) return;
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const cells = new Set<string>();
  // Плашки летят в слое размером ровно с видимую область сетки, и всё за её
  // краем обрезается. Без слоя они вылетали на поля страницы и поверх колонки
  // с днями — на снимке перелёта это выглядело мусором (15.09.2026).
  const frame = document.querySelector("[data-grid]")?.getBoundingClientRect();
  const layer = document.createElement("div");
  if (frame && !reduce) {
    layer.className = "pointer-events-none fixed z-50 overflow-hidden rounded-lg";
    Object.assign(layer.style, { left: `${frame.left}px`, top: `${frame.top}px`,
                                 width: `${frame.width}px`, height: `${frame.height}px` });
    document.body.appendChild(layer);
    window.setTimeout(() => layer.remove(), 2600);
  }
  moves.slice(0, 120).forEach((move, n) => {
    const [groupId, subjectId] = move.key.split("|");
    const classId = dir.groups[groupId]?.class_ids[0];
    if (!classId) return;
    const [day, period] = move.to.split("|").map(Number);
    cells.add(cellKey(classId, day, period));
    const from = rects.get(`${move.key}|${move.from}`);
    const target = document.querySelector(`[data-cell="${cellKey(classId, day, period)}"]`);
    if (reduce || !frame || !from || !target) return;
    const to = target.getBoundingClientRect();
    const ghost = document.createElement("div");
    ghost.textContent = short(dir.subjects[subjectId] ?? subjectId);
    ghost.className = "absolute rounded bg-pen px-1.5 py-0.5 font-narrow text-cell font-medium text-white shadow-pop";
    ghost.style.left = `${from.left - frame.left + 4}px`;
    ghost.style.top = `${from.top - frame.top + 4}px`;
    layer.appendChild(ghost);
    const dx = to.left - from.left, dy = to.top - from.top;
    const flight = ghost.animate(
      [
        { transform: "translate(0, 0) scale(0.9)", opacity: 0 },
        { transform: "translate(0, 0) scale(1)", opacity: 1, offset: 0.15 },
        { transform: `translate(${dx}px, ${dy}px) scale(1)`, opacity: 1, offset: 0.8 },
        { transform: `translate(${dx}px, ${dy}px) scale(0.9)`, opacity: 0 },
      ],
      { duration: 1000, delay: Math.min(n * 18, 1200), easing: "cubic-bezier(.2,.7,.2,1)", fill: "both" },
    );
    flight.onfinish = () => ghost.remove();
  });
  setFlash(cells);
  window.setTimeout(() => setFlash(new Set()), 2600);
}

function RebuildProgress({ rebuild, now, onStop }: {
  rebuild: { started: number; pinsCount: number; progress?: Progress; stopped?: boolean };
  now: number;
  onStop: () => void;
}) {
  const elapsed = Math.max(0, ((now || Date.now()) - rebuild.started) / 1000);
  const p = rebuild.progress;
  const found = p && Object.keys(p.metrics).length > 0;
  return (
    <Panel as="div" className="text-small">
      <p className="text-heading">Пересобираю вокруг закреплённых: {rebuild.pinsCount}</p>
      <div className="mt-3 h-1 overflow-hidden rounded-full bg-rule">
        <div className="h-full bg-pen transition-[width] duration-500"
             style={{ width: `${Math.min(100, (elapsed / REBUILD_SECONDS) * 100)}%` }} />
      </div>
      <p className="mt-2 text-pencil">
        {Math.round(elapsed)} с из {REBUILD_SECONDS}.{" "}
        {!found ? "Ищу законную сетку вокруг закреплённых…"
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
      <Button className="mt-3" disabled={rebuild.stopped} onClick={onStop}>
        {rebuild.stopped ? "Останавливаю…" : "Остановить и взять лучшее"}
      </Button>
    </Panel>
  );
}
