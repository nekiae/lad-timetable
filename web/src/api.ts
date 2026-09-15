// Клиент API. Один файл — чтобы форма данных сервера читалась в одном месте.

export type Doc = {
  tables: Record<string, Record<string, unknown>[]>;
  settings: Record<string, unknown>;
  wishes: Record<string, unknown>;
};

export type InputStep = {
  key: string;
  title: string;
  why: string;
  empty: string;
  count: number;
  done: boolean;
  blocked_by: string[];
  optional?: boolean;
};

export type InputState = {
  steps: InputStep[];
  next: string | null;
  rooms_verdict: string[];
  divided: string[];
  teacher_hours: Record<string, number>;
  options: { room_kinds: string[]; levels: string[]; lesson_kinds: string[] };
};

export type ImportReport = {
  imported: Record<string, number>;
  unknown_sheets: string[];
  unknown_columns: Record<string, string[]>;
  missing_columns: Record<string, string[]>;
};

/** Ответ действия ввода: школа целиком после сохранения. */
export type Saved = { doc: Doc; revision: number };

export type LessonDTO = {
  day: number;
  period: number;
  shift: number;
  group_id: string;
  subject_id: string;
  teacher_id: string;
  room_id: string | null;
  kind: string;
};

export type Violation = { rule: string; what: string; where: string };

export type Report = {
  teacher_gaps: number;
  class_gaps: number;
  teacher_days: number;
  class_spread: number;
  shortest_day: number;
  difficulty_spread: number | null;
  lessons_total: number;
  violations: Violation[];
  summary: Record<string, number>;
  norm_violations: number;
  structural_violations: number;
  logic: Logic;
};

/** Логика расписания сверх норм — lad/quality.py. */
export type Logic = {
  day_spread_max: number;
  classes_spread_3plus: number;
  monday_heavy: number;
  adjacent_two: number;
  three_in_row: number;
  teacher_single_days: number;
  teacher_longest_day: number;
};

/** Изменение для «что если». */
export type Change =
  | { kind: "teacher_day_off"; teacher: string; day: number }
  | { kind: "gym_plus" }
  | { kind: "preset"; preset: string }
  | { kind: "rule"; rule: string; value: string };

export type ComparisonSide = {
  id: string;
  lessons: LessonDTO[];
  seconds: number | null;
  metrics: Logic & { norms: number; conflicts: number; teacher_gaps: number; teacher_days: number; moved: number };
};

export type Comparison = {
  label: string;
  change: Change;
  mode: "keep" | "fresh";
  budget: number;
  stale: boolean;
  control: ComparisonSide;
  variant: ComparisonSide;
};

export type Directory = {
  name: string;
  days: { n: number; name: string }[];
  periods: number;
  classes: { id: string; name: string; parallel: number }[];
  groups: Record<string, { class_ids: string[]; part: string | null }>;
  teachers: Record<string, string>;
  subjects: Record<string, string>;
  rooms: Record<string, string>;
  /** Балл трудности предмета для класса: class_id → subject_id → балл. */
  difficulty: Record<string, Record<string, number>>;
  /** Рекомендованные дни пика нагрузки класса (п. 94 ССЭТ). */
  peak_days: Record<string, number[]>;
};

export type Schedule = {
  id: string;
  meta: { status?: string; seconds?: number; penalty?: number; relaxed?: string[] };
  created_at: number;
  stale: boolean;
  directory: Directory;
  lessons: LessonDTO[];
  report: Report | null;
};

/** Версия расписания в списке версий. */
export type ScheduleVersion = {
  id: string;
  created_at: number;
  title: string;
  name: string | null;
  summary: { norms: number; gaps: number; conflicts: number } | null;
  current: boolean;
  /** Составлена по прежним данным школы. */
  stale: boolean;
};

export type Reason = { text: string; source: string | null };

export type Verdict = {
  level: "ok" | "worse" | "no";
  blocking: Reason[];
  costs: Reason[];
  gains: Reason[];
  moved: number[];
  swapped: number[];
};

export type Candidate = {
  teacher_id: string;
  name: string;
  score: number;
  level: "best" | "good" | "possible";
  reasons: string[];
  costs: string[];
};

export type Need = {
  index: number;
  period: number;
  group_name: string;
  subject: string;
  room_id: string | null;
  candidates: Candidate[];
  note: string | null;
};

export type Progress = {
  stage: "search" | "improve";
  seconds: number;
  budget: number;
  solutions: number;
  penalty: number | null;
  bound: number | null;
  metrics: Record<string, number>;
  gap: number | null;
  /** Этап: черновик «ноль нарушений норм» или доводка удобства. */
  phase: "draft" | "polish";
  /** Снимок лучшей сетки: [строка нагрузки, день, урок]; не в каждом событии. */
  grid: number[][] | null;
  /** Секунды от старта задачи — общий отсчёт для всех этапов. */
  wall: number;
  /** Нарушения по каждой норме: какая именно держит хвост поиска. */
  norms: Record<string, number>;
};

/** Справочник для живой сетки: что за урок за строкой нагрузки из снимков. */
export type SearchSetup = {
  classes: string[];
  class_ids: string[];
  days: number[];
  periods: number;
  load: { classes: string[]; subject: string }[];
};

export type SolveDone = {
  type: "result" | "problems" | "error";
  status?: string;
  seconds?: number;
  relaxed?: string[];
  problems?: string[];
  error?: string;
  schedule_id: string | null;
};

/** Лист на выдачу: заголовок, подпись и строки таблицы — ровно как на экране. */
export type SheetDTO = { title: string; subtitle: string; rows: string[][] };

async function blob(res: Response): Promise<Blob> {
  if (!res.ok) {
    const text = await res.text();
    let detail: unknown = text;
    try {
      detail = JSON.parse(text).detail;
    } catch {
      /* ответ не JSON */
    }
    throw new Error(typeof detail === "string" ? detail : "Файл не собрался");
  }
  return res.blob();
}

/** Сохранить файл в загрузки. */
export function saveBlob(data: Blob, name: string) {
  const url = URL.createObjectURL(data);
  const link = Object.assign(document.createElement("a"), { href: url, download: name });
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    let detail: unknown = text;
    try {
      detail = JSON.parse(text).detail;
    } catch {
      /* ответ не JSON — показываем как есть */
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.json() as Promise<T>;
}

export const api = {
  schools: () =>
    call<{ id: string; name: string; updated_at: number; schedule_at: number | null }[]>("GET", "/schools"),
  createSchool: (name: string, fromExample: boolean) =>
    call<{ id: string }>("POST", "/schools", { name, from_example: fromExample }),
  school: (id: string) => call<{ id: string; revision: number; doc: Doc }>("GET", `/schools/${id}`),
  saveSchool: (id: string, doc: Doc) => call<{ revision: number }>("PUT", `/schools/${id}`, doc),
  check: (id: string) =>
    call<{
      problems: string[];
      warnings: string[];
      stats: Record<string, number>;
      /** Спортзалы: уроков физкультуры в неделю и мест в залах за один урок. */
      pe: { hours: number; gyms: number; seats: number; periods: number; days: number };
    }>("GET", `/schools/${id}/check`),
  input: (id: string) => call<InputState>("GET", `/schools/${id}/input`),
  generateClasses: (id: string, counts: Record<string, number>, sizes: Record<string, number>) =>
    call<Saved & { added: number }>("POST", `/schools/${id}/classes/generate`, { counts, sizes }),
  roomsSuggest: (id: string) =>
    call<{ regular: number; special: Record<string, number> }>("GET", `/schools/${id}/rooms/suggest`),
  generateRooms: (id: string, regular: number, special: Record<string, number>) =>
    call<Saved & { added: number }>("POST", `/schools/${id}/rooms/generate`, { regular, special }),
  subjectsFromPlan: (id: string) =>
    call<Saved & { added: number }>("POST", `/schools/${id}/subjects/from-plan`),
  loadFromPlan: (id: string) =>
    call<Saved & { added: number; unknown: string[] }>("POST", `/schools/${id}/load/from-plan`),
  assign: (id: string, body: { subject: string; teacher: string; classes: string[];
                               previous?: string | null; hours?: number | null }) =>
    call<Saved & { skipped: string[] }>("POST", `/schools/${id}/load/assign`, body),
  spread: (id: string, subject: string, teachers: string[]) =>
    call<Saved>("POST", `/schools/${id}/load/spread`, { subject, teachers }),
  rules: () =>
    call<{
      rules: { key: string; title: string; source: string | null; default: string }[];
      presets: { name: string; about: string }[];
      /** Предпочтения школы: уровень 0–3 («не важно» … «очень важно»). */
      preferences: { key: string; group: string; title: string; about: string; default: number }[];
    }>("GET", "/rules"),
  solve: (id: string, body: { budget: number; preset: string; rules?: Record<string, string>;
                               prefs?: Record<string, number>; pinned?: LessonDTO[]; hint?: LessonDTO[];
                               keep?: boolean }) =>
    call<{ job_id: string }>("POST", `/schools/${id}/solve`, body),
  stop: (jobId: string) => call<{ ok: boolean }>("POST", `/jobs/${jobId}/stop`),
  latest: (id: string) => call<Schedule>("GET", `/schools/${id}/schedules/latest`),
  schedule: (id: string, scheduleId: string) => call<Schedule>("GET", `/schools/${id}/schedules/${scheduleId}`),
  validate: (id: string, lessons: LessonDTO[]) =>
    call<Report>("POST", `/schools/${id}/validate`, { lessons }),
  heatmap: (id: string, lessons: LessonDTO[], index: number) =>
    call<Record<string, Verdict>>("POST", `/schools/${id}/heatmap`, { lessons, index }),
  move: (id: string, lessons: LessonDTO[], index: number, day: number, period: number) =>
    call<{ verdict: Verdict; lessons: LessonDTO[]; report: Report }>(
      "POST", `/schools/${id}/move`, { lessons, index, day, period }),
  substitutions: (id: string, teacherId: string, day: number, lessons: LessonDTO[]) =>
    call<{ teacher: string; day: number; day_name: string; needs: Need[] }>(
      "POST", `/schools/${id}/substitutions`, { teacher_id: teacherId, day, lessons }),
  saveEdited: (id: string, lessons: LessonDTO[], name?: string) =>
    call<{ id: string }>("POST", `/schools/${id}/schedules`, { lessons, name }),
  versions: (id: string) => call<ScheduleVersion[]>("GET", `/schools/${id}/schedules`),
  restoreVersion: (id: string, scheduleId: string) =>
    call<{ schedule_id: string }>("POST", `/schools/${id}/schedules/${scheduleId}/restore`),
  substitutionSheet: (id: string, format: "pdf" | "xlsx", sheet: SheetDTO) =>
    fetch(`/api/schools/${id}/substitutions/sheet.${format}`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(sheet),
    }).then(blob),
  printPdf: (id: string, by: "class" | "teacher", anonymize: boolean) =>
    fetch(`/api/schools/${id}/print.pdf?by=${by}&anonymize=${anonymize}`).then(blob),
  whatIf: (id: string, change: Change, mode: "keep" | "fresh") =>
    call<{ label: string; budget: number; control: string; variant: string; blocked?: string[] }>(
      "POST", `/schools/${id}/whatif`, { change, mode }),
  whatIfCompare: (id: string, control: string, variant: string) =>
    call<Comparison>("GET", `/schools/${id}/whatif?control=${control}&variant=${variant}`),
  whatIfApply: (id: string, control: string, variant: string) =>
    call<{ schedule_id: string; label: string }>("POST", `/schools/${id}/whatif/apply`, { control, variant }),

  /** Ход составления: снимки прогресса, затем итог. Возвращает функцию отписки. */
  watch(jobId: string, onProgress: (p: Progress) => void, onDone: (d: SolveDone) => void,
        onSetup?: (s: SearchSetup) => void) {
    const source = new EventSource(`/api/jobs/${jobId}/events`);
    if (onSetup) source.addEventListener("setup", (e) => onSetup(JSON.parse((e as MessageEvent).data)));
    source.addEventListener("progress", (e) => onProgress(JSON.parse((e as MessageEvent).data)));
    source.addEventListener("done", (e) => {
      source.close();
      onDone(JSON.parse((e as MessageEvent).data));
    });
    return () => source.close();
  },

  /** Данные школы в Excel: резервная копия и шаблон для заполнения. */
  async downloadData(id: string) {
    const res = await fetch(`/api/schools/${id}/data.xlsx`);
    if (!res.ok) throw new Error("Файл не скачался");
    const url = URL.createObjectURL(await res.blob());
    const link = Object.assign(document.createElement("a"), { href: url, download: "lad-dannye.xlsx" });
    link.click();
    URL.revokeObjectURL(url);
  },
  importData: (id: string, file: File) =>
    fetch(`/api/schools/${id}/data.xlsx`, { method: "POST", body: file }).then(async (res) => {
      const data = await res.json();
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail));
      return data as Saved & { report: ImportReport };
    }),

  async exportXlsx(id: string, lessons: LessonDTO[], anonymize: boolean) {
    const res = await fetch(`/api/schools/${id}/export.xlsx?anonymize=${anonymize}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lessons }),
    });
    const url = URL.createObjectURL(await res.blob());
    const link = Object.assign(document.createElement("a"), { href: url, download: "raspisanie.xlsx" });
    link.click();
    URL.revokeObjectURL(url);
  },
};
