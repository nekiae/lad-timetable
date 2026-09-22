import { useState } from "react";
import { api, type Doc } from "../api";
import { Button, Notice } from "../ui";

/** Одна адресная запись: кому → что → насколько. */
export type Aim = { scope: string; who: string; key: string; value: number | string };

export type Choice = {
  key: string;
  title: string;
  kind: "level" | "rule" | "number" | "day";
  about?: string;
  min?: number;
  max?: number;
  scopes?: string[];
};

const LEVELS: [number, string][] = [[0, "Не важно"], [1, "Немного"], [2, "Важно"], [3, "Очень"]];
const STRICT: [string, string][] = [["hard", "Жёстко"], ["soft", "Мягко"], ["off", "Не учитывать"]];
const DAYS = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота"];
const SCOPE_TITLES: Record<string, string> = {
  school: "Вся школа", parallel: "Параллель", class: "Класс",
  teacher: "Учитель", subject: "Предмет",
};

const field =
  "rounded border border-rule bg-sheet px-2 py-1.5 focus:border-pen focus:outline-none";

/** Пожелания с адресом.
 *
 * Общий ползунок на всю школу ломается о простое: у одиннадцатых 37 уроков
 * в неделю, у шестых 26. Ровные дни первым по силам, вторым нет — и выбирать
 * приходилось между «неровно у всех» и «не составилось вовсе». Здесь то же
 * пожелание адресуется классу, параллели, учителю или предмету, а частное
 * правило перебивает общее.
 */
export function TargetedPrefs({ id, doc, aims, onChange, choices }: {
  id: string;
  doc?: Doc;
  aims: Aim[];
  onChange: (rows: Aim[]) => void;
  choices: Choice[];
}) {
  const [saved, setSaved] = useState<"idle" | "saving" | "done">("idle");
  const column = (table: string, key: string) =>
    ((doc?.tables[table] ?? []) as Record<string, unknown>[])
      .map((r) => String(r[key] ?? "")).filter(Boolean);
  const classes = column("classes", "класс");
  const teachers = column("teachers", "ФИО");
  const subjects = [...new Set(column("subjects", "предмет"))];
  const parallels = [...new Set(classes.map((c) => c.match(/^\d+/)?.[0] ?? ""))].filter(Boolean);

  const choiceOf = (key: string) => choices.find((c) => c.key === key);
  const kindOf = (key: string) => choiceOf(key)?.kind ?? "level";
  const scopesOf = (key: string) =>
    choiceOf(key)?.scopes ?? ["school", "parallel", "class", "teacher"];

  function startValue(key: string): number | string {
    const kind = kindOf(key);
    if (kind === "rule") return "hard";
    if (kind === "day") return 1;
    if (kind === "number") return choiceOf(key)?.min ?? 6;
    return 3;
  }

  async function save(rows: Aim[]) {
    onChange(rows);
    setSaved("saving");
    await api.saveTargeted(id, rows);
    setSaved("done");
  }

  function update(n: number, patch: Partial<Aim>) {
    const rows = aims.map((row, i) => (i === n ? { ...row, ...patch } : row));
    // Сменили пожелание — прежние адрес и значение могут ему не подходить:
    // «предмет не в этот день» адресуется предмету, а не классу.
    if (patch.key) {
      rows[n].value = startValue(patch.key);
      const allowed = scopesOf(patch.key);
      if (!allowed.includes(rows[n].scope)) {
        rows[n].scope = allowed[0];
        rows[n].who = "";
      }
    }
    if (patch.scope === "school") rows[n].who = "";
    save(rows);
  }

  function whoOptions(scope: string): string[] {
    if (scope === "class") return classes;
    if (scope === "teacher") return teachers;
    if (scope === "subject") return subjects;
    if (scope === "parallel") return parallels;
    return [];
  }

  function valueCell(row: Aim, n: number) {
    const kind = kindOf(row.key);
    if (kind === "rule")
      return (
        <select className={field} value={String(row.value)}
                onChange={(e) => update(n, { value: e.target.value })}>
          {STRICT.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
        </select>
      );
    if (kind === "day")
      return (
        <select className={field} value={Number(row.value)}
                onChange={(e) => update(n, { value: Number(e.target.value) })}>
          {DAYS.map((name, i) => <option key={name} value={i + 1}>{name}</option>)}
        </select>
      );
    if (kind === "number")
      return (
        <input type="number" className={`${field} w-24`} value={Number(row.value)}
               min={choiceOf(row.key)?.min ?? 1} max={choiceOf(row.key)?.max ?? 12}
               onChange={(e) => update(n, { value: Number(e.target.value) })} />
      );
    return (
      <select className={field} value={Number(row.value)}
              onChange={(e) => update(n, { value: Number(e.target.value) })}>
        {LEVELS.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
      </select>
    );
  }

  return (
    <div className="mt-4">
      <p className="max-w-3xl text-pencil">
        То же, что ползунки выше, но не на всю школу сразу. Правило для класса сильнее
        правила для его параллели, а оно — сильнее общего. Так «ровные дни жёстко»
        достаётся одиннадцатым, которым это по силам, и не мешает шестым.
        Здесь же задаются числа: потолок уроков в день, «не позже такого-то урока»,
        «информатика не в понедельник».
      </p>

      {aims.length > 0 && (
        <table className="mt-4 w-full max-w-4xl border-separate border-spacing-y-1 text-left">
          <thead className="text-pencil">
            <tr>
              <th className="font-normal">Кому</th>
              <th className="font-normal">Кто именно</th>
              <th className="font-normal">Что</th>
              <th className="font-normal">Насколько</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {aims.map((row, n) => (
              <tr key={n}>
                <td className="pr-2">
                  <select className={field} value={row.scope}
                          onChange={(e) => update(n, { scope: e.target.value, who: "" })}>
                    {scopesOf(row.key).map((v) => (
                      <option key={v} value={v}>{SCOPE_TITLES[v] ?? v}</option>
                    ))}
                  </select>
                </td>
                <td className="pr-2">
                  {row.scope === "school" ? (
                    <span className="text-pencil">—</span>
                  ) : (
                    <select className={field} value={row.who}
                            onChange={(e) => update(n, { who: e.target.value })}>
                      <option value="">выберите</option>
                      {whoOptions(row.scope).map((v) => <option key={v} value={v}>{v}</option>)}
                    </select>
                  )}
                </td>
                <td className="pr-2">
                  <select className={field} value={row.key}
                          onChange={(e) => update(n, { key: e.target.value })}
                          title={choiceOf(row.key)?.about}>
                    {choices.map((c) => <option key={c.key} value={c.key}>{c.title}</option>)}
                  </select>
                </td>
                <td className="pr-2">{valueCell(row, n)}</td>
                <td>
                  <button type="button" className="text-pencil underline-offset-4 hover:underline"
                          onClick={() => save(aims.filter((_, i) => i !== n))}>убрать</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {aims.some((row) => row.scope !== "school" && !row.who) && (
        <Notice tone="worse" className="mt-3">
          У записи не выбран адресат — она не применится.
        </Notice>
      )}

      {aims.length > 0 && choiceOf(aims[aims.length - 1].key)?.about && (
        <p className="mt-3 max-w-3xl text-pencil">
          {choiceOf(aims[aims.length - 1].key)?.about}
        </p>
      )}

      <div className="mt-3 flex items-center gap-3">
        <Button onClick={() => {
          const key = choices[0]?.key ?? "even_days";
          const scope = scopesOf(key)[0];
          save([...aims, {
            scope, who: scope === "parallel" ? (parallels.at(-1) ?? "") : "",
            key, value: startValue(key),
          }]);
        }}>Добавить пожелание</Button>
        {saved === "saving" && <span className="text-pencil">сохраняю…</span>}
        {saved === "done" && <span className="text-pencil">сохранено</span>}
      </div>
    </div>
  );
}
