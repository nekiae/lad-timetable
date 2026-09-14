// Клиент API. Один файл — чтобы форма данных сервера читалась в одном месте.

export type Doc = {
  tables: Record<string, Record<string, unknown>[]>;
  settings: Record<string, unknown>;
  wishes: Record<string, unknown>;
};

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

export type Progress = {
  stage: "search" | "improve";
  seconds: number;
  budget: number;
  solutions: number;
  penalty: number | null;
  bound: number | null;
  metrics: Record<string, number>;
  gap: number | null;
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
  schools: () => call<{ id: string; name: string; updated_at: number }[]>("GET", "/schools"),
  createSchool: (name: string, fromExample: boolean) =>
    call<{ id: string }>("POST", "/schools", { name, from_example: fromExample }),
  school: (id: string) => call<{ id: string; revision: number; doc: Doc }>("GET", `/schools/${id}`),
  saveSchool: (id: string, doc: Doc) => call<{ revision: number }>("PUT", `/schools/${id}`, doc),
  check: (id: string) =>
    call<{ problems: string[]; warnings: string[]; stats: Record<string, number> }>(
      "GET", `/schools/${id}/check`),
  rules: () =>
    call<{
      rules: { key: string; title: string; source: string | null; default: string }[];
      presets: { name: string; about: string }[];
    }>("GET", "/rules"),
  solve: (id: string, body: { budget: number; preset: string; rules?: Record<string, string>;
                               pinned?: LessonDTO[] }) =>
    call<{ job_id: string }>("POST", `/schools/${id}/solve`, body),
  stop: (jobId: string) => call<{ ok: boolean }>("POST", `/jobs/${jobId}/stop`),
  latest: (id: string) => call<Schedule>("GET", `/schools/${id}/schedules/latest`),
  validate: (id: string, lessons: LessonDTO[]) =>
    call<Report>("POST", `/schools/${id}/validate`, { lessons }),
  saveEdited: (id: string, lessons: LessonDTO[]) =>
    call<{ id: string }>("POST", `/schools/${id}/schedules`, { lessons }),

  /** Ход составления: снимки прогресса, затем итог. Возвращает функцию отписки. */
  watch(jobId: string, onProgress: (p: Progress) => void, onDone: (d: SolveDone) => void) {
    const source = new EventSource(`/api/jobs/${jobId}/events`);
    source.addEventListener("progress", (e) => onProgress(JSON.parse((e as MessageEvent).data)));
    source.addEventListener("done", (e) => {
      source.close();
      onDone(JSON.parse((e as MessageEvent).data));
    });
    return () => source.close();
  },

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
