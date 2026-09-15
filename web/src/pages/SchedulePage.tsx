import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { api, type Directory, type LessonDTO, type Logic, type Progress, type Report, type Schedule, type ScheduleVersion,
         type Verdict } from "../api";
import { Button, ButtonLink, EmptyState, Notice, Panel, Reasons, cx, inputClass, when } from "../ui";
import { Key, MOD } from "../CommandPalette";
import { DifficultyMap } from "./DifficultyMap";

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

export function short(name: string) {
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
  // Подсветка учителя по всей сетке: наведение на фамилию — пока курсор на ней,
  // из поиска ⌘K (?teacher=) — пока не снимут Esc. Колонка класса из поиска — ?class=.
  const [searchParams, setSearchParams] = useSearchParams();
  const lockedTeacher = searchParams.get("teacher");
  const focusClass = searchParams.get("class");
  const [hoverTeacher, setHoverTeacher] = useState<string | null>(null);
  // Курсор клавиатуры: номер класса в сетке, день и урок.
  const [cursor, setCursor] = useState<{ c: number; day: number; period: number } | null>(null);
  const [showDifficulty, setShowDifficulty] = useState(() => {
    try {
      return localStorage.getItem("lad.difficulty") === "1";
    } catch {
      return false;
    }
  });
  // Перетаскивание урока мышью. Начало — в ref: его читают обработчики окна.
  // Призрак под курсором — в состоянии: его надо рисовать.
  const dragStart = useRef<{ index: number; x: number; y: number; moved: boolean } | null>(null);
  const [drag, setDrag] = useState<{ index: number; x: number; y: number; over: string | null } | null>(null);
  const suppressClick = useRef(false);
  // Где курсор при перетаскивании — для прокрутки сетки у края: неделя
  // класса выше экрана, и до вторника без прокрутки не дотащить.
  const dragPointer = useRef<{ x: number; y: number } | null>(null);
  // Запрос подсветки недели: при перетаскивании урок отпускают раньше, чем
  // пришёл ответ, — тогда ход ждёт этот же запрос, а не шлёт второй.
  const heatRequest = useRef<{ index: number; promise: Promise<Record<string, Verdict>> } | null>(null);
  // Обработчики окна вешаются один раз и зовут свежие функции из последней отрисовки.
  const onKey = useRef<(e: KeyboardEvent) => void>();
  const onPointerMove = useRef<(e: PointerEvent) => void>();
  const onPointerUp = useRef<(e: PointerEvent) => void>();

  useEffect(() => {
    const key = (e: KeyboardEvent) => onKey.current?.(e);
    const move = (e: PointerEvent) => onPointerMove.current?.(e);
    const up = (e: PointerEvent) => onPointerUp.current?.(e);
    window.addEventListener("keydown", key);
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    return () => {
      window.removeEventListener("keydown", key);
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
  }, []);

  // Версии: ?version= открывает прежнюю, без него — текущую (последнюю сохранённую).
  const version = searchParams.get("version");
  const [versions, setVersions] = useState<ScheduleVersion[]>();
  const [showVersions, setShowVersions] = useState(false);
  const [naming, setNaming] = useState(false);
  const [versionName, setVersionName] = useState("");
  // Убрать ?version= из адреса, не перезагружая сетку: после сохранения или
  // пересборки открытая сетка УЖЕ текущая, а перезагрузка стёрла бы «Отменить ход».
  const skipNextLoad = useRef(false);
  const refreshVersions = () => api.versions(id).then(setVersions).catch(() => undefined);

  useEffect(() => {
    if (skipNextLoad.current) {
      skipNextLoad.current = false;
      return;
    }
    setHistory([]);
    setSelected(null);
    setHeat(null);
    setPreview(null);
    setLast(null);
    setPins([]);
    setRebuildResult(null);
    setSaved("idle");
    (version ? api.schedule(id, version) : api.latest(id))
      .then((s) => {
        setSchedule(s);
        setLessons(s.lessons);
        setReport(s.report);
      })
      .catch(() => setSchedule(null));
    api.school(id).then((s) => setSettings(s.doc.settings)).catch(() => undefined);
    refreshVersions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, version]);

  // Несохранённые ходы не теряются молча: браузер переспросит перед уходом.
  const unsaved = history.length > 0;
  useEffect(() => {
    if (!unsaved) return;
    const warn = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [unsaved]);

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

  // Из поиска: прокрутить к колонке класса или к первому уроку учителя.
  useEffect(() => {
    if (!dir) return;
    let target: Element | null = null;
    if (focusClass) target = document.querySelector(`th[data-class="${focusClass}"]`);
    else if (lockedTeacher) {
      const first = lessons.filter((l) => l.teacher_id === lockedTeacher)
        .sort((a, b) => a.day - b.day || a.period - b.period)[0];
      const classId = first && dir.groups[first.group_id]?.class_ids[0];
      if (classId) target = document.querySelector(`[data-cell="${cellKey(classId, first.day, first.period)}"]`);
    }
    target?.scrollIntoView({ block: "nearest", inline: "center", behavior: "smooth" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusClass, lockedTeacher, dir]);

  // Прокрутка сетки, пока урок держат у её края: чем ближе к краю, тем быстрее.
  const dragging = drag !== null;
  useEffect(() => {
    if (!dragging) return;
    const timer = window.setInterval(() => {
      const box = document.querySelector<HTMLElement>("[data-grid]");
      const at = dragPointer.current;
      if (!box || !at) return;
      const r = box.getBoundingClientRect();
      const edge = 48;
      const speed = (d: number) => (d < edge ? Math.round(((edge - d) / edge) * 24) : 0);
      const dy = speed(at.y - r.top - 40) ? -speed(at.y - r.top - 40) : speed(r.bottom - at.y);
      const dx = speed(at.x - r.left - 48) ? -speed(at.x - r.left - 48) : speed(r.right - at.x);
      if (dx || dy) box.scrollBy(dx, dy);
    }, 16);
    return () => window.clearInterval(timer);
  }, [dragging]);

  useEffect(() => {
    const c = cursor && dir?.classes[cursor.c];
    if (!c) return;
    document.querySelector(`[data-cell="${cellKey(c.id, cursor.day, cursor.period)}"]`)
      ?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [cursor, dir]);

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

  // force — не снимать выбор, если урок уже выбран (начало перетаскивания).
  async function pick(index: number, force = false) {
    if (selected === index) {
      if (force) return;
      setSelected(null);
      setHeat(null);
      heatRequest.current = null;
      return;
    }
    setSelected(index);
    setHeat(null);
    setPreview(null);
    setLast(null);
    const promise = api.heatmap(id, lessons, index);
    heatRequest.current = { index, promise };
    const result = await promise;
    if (heatRequest.current?.index === index) setHeat(result);
  }

  function place(day: number, period: number) {
    if (selected === null || !heat) return;
    return placeAt(selected, heat, day, period);
  }

  async function placeAt(index: number, map: Record<string, Verdict>, day: number, period: number) {
    const verdict = map[`${day}-${period}`];
    if (!verdict || verdict.level === "no") {
      setLast(verdict ? { verdict, applied: false, target: { index, day, period } } : null);
      return;
    }
    const result = await api.move(id, lessons, index, day, period);
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

  function dropVersionParam() {
    if (!version) return;
    skipNextLoad.current = true;
    setSearchParams((p) => {
      p.delete("version");
      return p;
    }, { replace: true });
  }

  async function save() {
    setSaved("saving");
    const { id: savedId } = await api.saveEdited(id, lessons, versionName);
    setHistory([]);
    setSaved("saved");
    setNaming(false);
    setVersionName("");
    setLast(null); // карточка прошлого хода после сохранения — уже не новость
    setSchedule((s) => (s ? { ...s, id: savedId, meta: { status: "EDITED" } } : s));
    dropVersionParam();
    refreshVersions();
  }

  function openVersion(versionId: string) {
    setSearchParams((p) => {
      if (versions?.[0]?.id === versionId) p.delete("version");
      else p.set("version", versionId);
      p.delete("teacher");
      p.delete("class");
      return p;
    });
  }

  async function restoreOpened() {
    if (!schedule) return;
    const { schedule_id } = await api.restoreVersion(id, schedule.id);
    setSchedule((s) => (s ? { ...s, id: schedule_id } : s));
    dropVersionParam();
    refreshVersions();
  }

  const clearFocus = () => setSearchParams((p) => {
    p.delete("teacher");
    p.delete("class");
    return p;
  });

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
        dropVersionParam();
        refreshVersions();
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
  const activeTeacher = selected === null && !drag ? hoverTeacher ?? lockedTeacher : null;

  function toggleDifficulty() {
    setShowDifficulty((on) => {
      try {
        localStorage.setItem("lad.difficulty", on ? "0" : "1");
      } catch {
        /* нет хранилища — переключатель просто не запомнится */
      }
      return !on;
    });
  }

  // Клавиатура: стрелки — курсор по сетке, Enter — выбрать урок или поставить
  // выбранный в клетку под курсором, Esc — снять всё, ⌘Z — отменить ход.
  onKey.current = (e) => {
    const target = e.target as HTMLElement;
    if (target.closest?.("input, textarea, select, [role=dialog]") || rebuild) return;
    const mod = e.metaKey || e.ctrlKey;
    if (mod && e.key.toLowerCase() === "s") {
      e.preventDefault();
      if (history.length) setNaming(true);
      return;
    }
    if (mod && !e.shiftKey && e.key.toLowerCase() === "z") {
      if (history.length) {
        e.preventDefault();
        undo();
      }
      return;
    }
    if (mod || e.altKey) return;
    if (e.key === "Escape") {
      setSelected(null);
      setHeat(null);
      setPreview(null);
      setLast(null);
      setCursor(null);
      setHoverTeacher(null);
      heatRequest.current = null;
      setNaming(false);
      if (lockedTeacher || focusClass) clearFocus();
      return;
    }
    const step = ({ ArrowUp: [0, -1], ArrowDown: [0, 1], ArrowLeft: [-1, 0], ArrowRight: [1, 0] } as
      Record<string, [number, number]>)[e.key];
    if (step) {
      e.preventDefault();
      const rows = dir.days.flatMap((d) => Array.from({ length: dir.periods }, (_, p) => ({ day: d.n, period: p + 1 })));
      let next: { c: number; day: number; period: number };
      if (cursor) {
        const row = rows.findIndex((r) => r.day === cursor.day && r.period === cursor.period);
        const r = rows[Math.min(rows.length - 1, Math.max(0, row + step[1]))];
        next = { c: Math.min(dir.classes.length - 1, Math.max(0, cursor.c + step[0])), day: r.day, period: r.period };
      } else if (selected !== null) {
        const l = lessons[selected];
        const c = dir.classes.findIndex((x) => dir.groups[l.group_id]?.class_ids.includes(x.id));
        next = { c: Math.max(0, c), day: l.day, period: l.period };
      } else {
        next = { c: 0, ...rows[0] };
      }
      setCursor(next);
      const key = `${next.day}-${next.period}`;
      const verdict = heat?.[key];
      setPreview(selected !== null && verdict && selectedClasses.has(dir.classes[next.c].id) ? { key, verdict } : null);
      return;
    }
    if (e.key === "Enter" && cursor && !target.closest?.("button, a")) {
      e.preventDefault();
      const classId = dir.classes[cursor.c].id;
      const cell = grid.get(`${classId}|${cursor.day}|${cursor.period}`) ?? [];
      if (selected !== null && selectedClasses.has(classId) && !cell.includes(selected)) place(cursor.day, cursor.period);
      else if (cell.length) pick(cell[0]);
    }
  };

  const cellUnder = (e: PointerEvent) =>
    (document.elementFromPoint(e.clientX, e.clientY) as HTMLElement | null)
      ?.closest<HTMLElement>("td[data-cell]")?.dataset.cell ?? null;

  // Перетаскивание: сдвинул урок на 6 px — он выбран, неделя класса подсвечена,
  // под курсором призрак цвета клетки. Отпустил на своём классе — тот же ход,
  // что щелчком: зелёная и жёлтая меняют уроки местами, на красной — карточка
  // «Сюда нельзя» с кнопкой «Поставить сюда и пересобрать остальное».
  onPointerMove.current = (e) => {
    const start = dragStart.current;
    if (!start) return;
    if (!start.moved) {
      if (Math.hypot(e.clientX - start.x, e.clientY - start.y) < 6) return;
      start.moved = true;
      setHoverTeacher(null);
      pick(start.index, true);
    }
    dragPointer.current = { x: e.clientX, y: e.clientY };
    setDrag({ index: start.index, x: e.clientX, y: e.clientY, over: cellUnder(e) });
  };

  onPointerUp.current = async (e) => {
    const start = dragStart.current;
    dragStart.current = null;
    dragPointer.current = null;
    if (!start?.moved) return;
    // Щелчок, который браузер пришлёт следом за отпусканием, — не выбор урока.
    suppressClick.current = true;
    window.setTimeout(() => { suppressClick.current = false; }, 0);
    setDrag(null);
    const cell = cellUnder(e);
    if (!cell) return;
    const [classId, d, p] = cell.split("|");
    const day = Number(d), period = Number(p);
    const lesson = lessons[start.index];
    if (!dir.groups[lesson.group_id]?.class_ids.includes(classId) || (lesson.day === day && lesson.period === period)) return;
    const request = heatRequest.current;
    if (request?.index !== start.index) return;
    placeAt(start.index, await request.promise, day, period);
  };

  const dragOver = drag?.over?.split("|");
  const dragLevel = drag && dragOver && heat && selected === drag.index && selectedClasses.has(dragOver[0])
    ? heat[`${dragOver[1]}-${dragOver[2]}`]?.level : undefined;

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
          <button type="button" aria-pressed={showDifficulty} onClick={toggleDifficulty}
                  className={cx("inline-flex items-center rounded border px-4 py-2 font-medium transition-colors duration-150",
                                showDifficulty ? "border-pen bg-pen-soft text-pen" : "border-rule bg-sheet hover:border-pencil")}>
            Трудность по дням
          </button>
          <Button disabled={!history.length} onClick={undo}>Отменить ход</Button>
          <Button variant={history.length ? "primary" : "quiet"}
                  disabled={!history.length || saved === "saving"} onClick={() => setNaming(true)}>
            {saved === "saved" ? "Версия сохранена" : "Сохранить версию"}
          </Button>
          <button type="button" aria-pressed={showVersions} onClick={() => setShowVersions((on) => !on)}
                  className={cx("inline-flex items-center rounded border px-4 py-2 font-medium transition-colors duration-150",
                                showVersions ? "border-pen bg-pen-soft text-pen" : "border-rule bg-sheet hover:border-pencil")}>
            Версии{versions ? ` (${versions.length})` : ""}
          </button>
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

      {/* Открыта не текущая версия: всё остальное (замены, печать, «Что если»)
          работает с текущей — об этом надо сказать, а не молча показать старую сетку. */}
      {versions && versions[0] && schedule.id !== versions[0].id && history.length === 0 && (
        <Notice tone="info" className="mt-4" title={`Открыта версия от ${when(schedule.created_at)}`}>
          <p>Текущая — от {when(versions[0].created_at)}. Замены, печать и «Что если» берут текущую.</p>
          <div className="mt-2 flex flex-wrap gap-2">
            <Button onClick={restoreOpened}>Сделать эту версию текущей</Button>
            <Button onClick={() => openVersion(versions[0].id)}>Открыть текущую</Button>
          </div>
        </Notice>
      )}

      {schedule.stale && (
        <Notice tone="worse" className="mt-4">
          Данные школы изменились после составления. Сетка ниже — по прежним данным.
        </Notice>
      )}

      {showDifficulty && (
        <DifficultyMap dir={dir} lessons={lessons} onClass={(classId) => setSearchParams((p) => {
          p.delete("teacher");
          p.set("class", classId);
          return p;
        })} />
      )}

      <div className="mt-5 flex gap-6 max-lg:flex-col">
        <div data-grid className={cx("min-w-0 flex-1 overflow-auto rounded-lg border border-rule bg-sheet transition-opacity duration-300",
                           rebuild && "pointer-events-none opacity-60", drag && "cursor-grabbing")}
             style={{ maxHeight: "calc(100vh - 180px)" }}>
          <table className="select-none border-separate border-spacing-0 font-narrow text-cell">
            <thead>
              <tr>
                <th className="sticky left-0 top-0 z-30 border-b border-r border-rule bg-paper" />
                {dir.classes.map((c) => (
                  <th key={c.id} scope="col" data-class={c.id}
                      className={cx(
                        "sticky top-0 z-20 min-w-[88px] border-b border-r border-rule px-2 py-2 text-left text-small font-semibold",
                        selectedClasses.has(c.id) || focusClass === c.id ? "bg-pen-soft text-pen" : "bg-paper")}>
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
                        const cursorHere = cursor !== null && dir.classes[cursor.c]?.id === c.id
                          && cursor.day === day.n && cursor.period === period;
                        const teacherHere = activeTeacher !== null && cell.some((i) => lessons[i].teacher_id === activeTeacher);
                        return (
                          <td key={c.id} data-cell={cellKey(c.id, day.n, period)}
                              onMouseEnter={() => target && setPreview({ key, verdict })}
                              onMouseLeave={() => target && setPreview(null)}
                              onClick={() => {
                                if (suppressClick.current) return;
                                if (target && !isSource) place(day.n, period);
                                else if (cell.length) pick(cell[0]);
                              }}
                              className={cx(
                                "h-11 cursor-pointer border-r border-rule px-1.5 align-top",
                                dayBorder(period),
                                isSource && "outline outline-2 -outline-offset-2 outline-pen",
                                !isSource && cursorHere && "outline-dashed outline-2 -outline-offset-2 outline-pen",
                                flash.has(cellKey(c.id, day.n, period)) && "cell-flash",
                                // Своя клетка не красится: «можно» на месте урока ничего не значит,
                                // а зелёный призрак над ней обещал ход, которого не будет.
                                target && !isSource ? TINT[verdict.level]
                                  : teacherHere ? "bg-pen-soft"
                                    : focusClass === c.id ? "bg-pen-soft/40 hover:bg-paper" : "hover:bg-paper")}>
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
                                     onPointerDown={(e) => {
                                       if (e.button === 0 && e.pointerType !== "touch" && !rebuild)
                                         dragStart.current = { index: same[0], x: e.clientX, y: e.clientY, moved: false };
                                     }}
                                     className={cx("py-0.5", isPinned(l) && "-ml-1.5 border-l-[3px] border-pen pl-1",
                                                   drag?.index === same[0] && "opacity-40")}>
                                  <div className="font-medium">{short(subject)}{part ? ` (${part})` : ""}</div>
                                  <div className="text-pencil">
                                    {same.map((i, n) => (
                                      <span key={i}>
                                        {n > 0 && " / "}
                                        <span onMouseEnter={() => !dragStart.current && setHoverTeacher(lessons[i].teacher_id)}
                                              onMouseLeave={() => setHoverTeacher(null)}
                                              className={cx("hover:text-pen",
                                                            activeTeacher === lessons[i].teacher_id && "font-semibold text-pen")}>
                                          {teacherName(lessons[i].teacher_id)}
                                        </span>
                                      </span>
                                    ))}
                                  </div>
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
          {naming && history.length > 0 && (
            <Panel as="div" className="text-small">
              <form onSubmit={(e) => { e.preventDefault(); save(); }}>
                <label className="block">
                  <span className="text-heading">Сохранить версию</span>
                  <span className="mt-1 block text-pencil">Название — по желанию, чтобы узнать версию в списке.</span>
                  <input autoFocus value={versionName} onChange={(e) => setVersionName(e.target.value)}
                         placeholder="Например, после замены Ивановой" className={cx(inputClass, "mt-2")} />
                </label>
                <div className="mt-3 flex flex-wrap gap-2">
                  <Button type="submit" variant="primary" disabled={saved === "saving"}>
                    {saved === "saving" ? "Сохраняю…" : "Сохранить"}
                  </Button>
                  <Button onClick={() => setNaming(false)}>Отмена</Button>
                </div>
              </form>
            </Panel>
          )}
          {showVersions && versions && (
            <VersionsPanel versions={versions} opened={schedule.id} blocked={history.length > 0}
                           onOpen={openVersion} onClose={() => setShowVersions(false)} />
          )}
          {activeTeacher && dir.teachers[activeTeacher] && !rebuild && (
            <TeacherCard name={hideNames ? `Учитель ${teacherIndex.get(activeTeacher)}` : dir.teachers[activeTeacher]}
                         dir={dir} lessons={lessons} teacherId={activeTeacher}
                         locked={activeTeacher === lockedTeacher} onClear={clearFocus} />
          )}
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
                Щёлкните урок или перетащите его мышью. Клетки его класса подсветятся: зелёные — можно поставить,
                жёлтые — можно, но станет хуже, красные — нельзя. Щелчок по клетке меняет
                уроки местами. Урок можно закрепить — и пересобрать всё остальное вокруг
                закреплённых. Наведите на фамилию — подсветятся все уроки учителя.
              </p>
              <ul className="mt-3 space-y-1.5 text-pencil">
                <li><Key>←</Key> <Key>→</Key> <Key>↑</Key> <Key>↓</Key> по сетке</li>
                <li><Key>Enter</Key> выбрать урок, поставить в клетку</li>
                <li><Key>Esc</Key> снять выбор и подсветку</li>
                <li><Key>{MOD} Z</Key> отменить ход</li>
                <li><Key>{MOD} K</Key> найти класс или учителя</li>
              </ul>
            </Panel>
          )}
          {selected === null && !shown && !rebuild && report?.logic && (
            <LogicCard logic={report.logic} classes={dir.classes.length} id={id} />
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

      {drag && (
        <div className={cx("pointer-events-none fixed z-50 rounded px-2 py-1 font-narrow text-cell font-medium text-white shadow-pop",
                           dragLevel === "ok" ? "bg-ok" : dragLevel === "worse" ? "bg-worse" : dragLevel === "no" ? "bg-no" : "bg-pen")}
             style={{ left: drag.x + 12, top: drag.y + 12 }}>
          {short(dir.subjects[lessons[drag.index]?.subject_id] ?? "")}
          {dragLevel === "no" && " — нельзя"}
        </div>
      )}
    </div>
  );
}

// Версии расписания: каждое составление, пересборка и сохранённая правка.
// Открыть можно любую; пока есть несохранённые ходы — нельзя, иначе они пропадут.
function VersionsPanel({ versions, opened, blocked, onOpen, onClose }: {
  versions: ScheduleVersion[]; opened: string; blocked: boolean;
  onOpen: (id: string) => void; onClose: () => void;
}) {
  return (
    <Panel as="div" className="text-small">
      <div className="flex items-baseline justify-between gap-3">
        <p className="text-heading">Версии расписания</p>
        <button type="button" className="text-pen underline-offset-4 hover:underline" onClick={onClose}>скрыть</button>
      </div>
      {blocked && <p className="mt-2 text-worse">Есть несохранённые ходы — сохраните или отмените их, чтобы открыть другую версию.</p>}
      <ul className="mt-3 max-h-[60vh] space-y-1.5 overflow-auto">
        {versions.map((v) => {
          const isOpen = v.id === opened;
          return (
            <li key={v.id}>
              <button type="button" disabled={blocked || isOpen} onClick={() => onOpen(v.id)}
                      className={cx("w-full rounded border px-3 py-2 text-left transition-colors duration-150",
                                    isOpen ? "border-pen bg-pen-soft" : "border-rule bg-sheet enabled:hover:border-pencil",
                                    blocked && !isOpen && "opacity-60")}>
                <span className="flex items-baseline justify-between gap-2">
                  <span className="font-medium">{v.name || v.title}</span>
                  {v.current && <span className="shrink-0 text-ok">текущая</span>}
                </span>
                {v.name && <span className="block text-pencil">{v.title}</span>}
                <span className="block text-pencil">
                  {when(v.created_at)}
                  {v.summary && `. Нарушений норм ${v.summary.norms}, окон ${v.summary.gaps}`}
                  {v.summary?.conflicts ? `, конфликтов ${v.summary.conflicts}` : ""}
                </span>
                {v.stale && <span className="block text-worse">по прежним данным школы</span>}
              </button>
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}

// Учитель под подсветкой: неделя цифрами — чтобы окна и «день ради одного
// урока» были видны без подсчёта по сетке.
function TeacherCard({ name, dir, lessons, teacherId, locked, onClear }: {
  name: string; dir: Directory; lessons: LessonDTO[]; teacherId: string; locked: boolean; onClear: () => void;
}) {
  const byDay = new Map<number, Set<number>>();
  for (const l of lessons) {
    if (l.teacher_id !== teacherId) continue;
    byDay.set(l.day, (byDay.get(l.day) ?? new Set()).add(l.period));
  }
  let total = 0, gaps = 0;
  for (const periods of byDay.values()) {
    total += periods.size;
    gaps += Math.max(...periods) - Math.min(...periods) + 1 - periods.size;
  }
  return (
    <Panel as="div" className="border-pen/40 text-small">
      <p className="text-heading">{name}</p>
      <p className="mt-1">
        {total} {plural(total, "урок", "урока", "уроков")} в неделю, {byDay.size}{" "}
        {plural(byDay.size, "день", "дня", "дней")} в школе, окон {gaps}.
      </p>
      <p className="mt-1 text-pencil">
        {dir.days.map((d) => `${d.name.slice(0, 2)} ${byDay.get(d.n)?.size ?? 0}`).join(", ")}
      </p>
      {locked ? (
        <Button className="mt-3" onClick={onClear}>Снять подсветку</Button>
      ) : (
        <p className="mt-2 text-pencil">Чтобы подсветка осталась, найдите учителя через <Key>{MOD} K</Key>.</p>
      )}
    </Panel>
  );
}

// «1 урок», «3 урока», «5 уроков».
const plural = (n: number, one: string, few: string, many: string) => {
  const d = n % 10, h = n % 100;
  return d === 1 && h !== 11 ? one : d >= 2 && d <= 4 && (h < 12 || h > 14) ? few : many;
};

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

// Логика расписания сверх норм (lad/quality.py): то, что завуч заметит
// первым, хотя норм на это нет. Цифры пересчитываются после каждого хода.
function LogicCard({ logic, classes, id }: { logic: Logic; classes: number; id: string }) {
  const rows: [string, number | string][] = [
    ["Классов, где дни отличаются на 3+ урока", `${logic.classes_spread_3plus} из ${classes}`],
    ["Самый трудный день — понедельник", logic.monday_heavy],
    ["Предмет на 2 часа в соседние дни", logic.adjacent_two],
    ["Предмет на 3 часа три дня подряд", logic.three_in_row],
    ["Выходов учителя ради одного урока", logic.teacher_single_days],
    ["Самый длинный день учителя, уроков", logic.teacher_longest_day],
  ];
  return (
    <Panel as="div" className="text-small">
      <p className="text-heading">Логика расписания</p>
      <p className="mt-1 text-pencil">Норм на это нет, но завуч и учителя заметят первым.</p>
      <dl className="mt-2 divide-y divide-rule">
        {rows.map(([label, value]) => (
          <div key={label} className="flex items-baseline justify-between gap-3 py-1.5">
            <dt className="min-w-0">{label}</dt>
            <dd className="shrink-0 font-semibold">{value}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-3">
        <Link to={`/s/${id}/whatif`} className="font-medium text-pen underline-offset-4 hover:underline">
          Проверить, что будет, если…
        </Link>
      </p>
    </Panel>
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
