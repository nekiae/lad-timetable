import { useState } from "react";
import { api, type Doc } from "../api";
import { Button, Notice } from "../ui";

/** Одна адресная запись: кому → что → насколько. */
export type Aim = { scope: string; who: string; key: string; value: number | string };

type Choice = { key: string; title: string; kind: "level" | "rule" };

const LEVELS: [number, string][] = [[0, "Не важно"], [1, "Немного"], [2, "Важно"], [3, "Очень"]];
const STRICT: [string, string][] = [["hard", "Жёстко"], ["soft", "Мягко"], ["off", "Не учитывать"]];
const SCOPES: [string, string][] = [
  ["school", "Вся школа"], ["parallel", "Параллель"], ["class", "Класс"], ["teacher", "Учитель"],
];

const field =
  "rounded border border-rule bg-sheet px-2 py-1.5 focus:border-pen focus:outline-none";

/** Пожелания с адресом.
 *
 * Общий ползунок на всю школу ломается о простое: у одиннадцатых 37 уроков
 * в неделю, у шестых 26. Ровные дни первым по силам, вторым нет — и выбирать
 * приходилось между «неровно у всех» и «не составилось вовсе». Здесь то же
 * пожелание адресуется классу, параллели или учителю, а частное правило
 * перебивает общее.
 */
export function TargetedPrefs({ id, doc, aims, onChange, choices }: {
  id: string;
  doc?: Doc;
  aims: Aim[];
  onChange: (rows: Aim[]) => void;
  choices: Choice[];
}) {
  const [saved, setSaved] = useState<"idle" | "saving" | "done">("idle");
  const classes = ((doc?.tables.classes ?? []) as Record<string, unknown>[])
    .map((r) => String(r["класс"] ?? "")).filter(Boolean);
  const teachers = ((doc?.tables.teachers ?? []) as Record<string, unknown>[])
    .map((r) => String(r["ФИО"] ?? "")).filter(Boolean);
  const parallels = [...new Set(classes.map((c) => c.match(/^\d+/)?.[0] ?? ""))].filter(Boolean);

  const kindOf = (key: string) => choices.find((c) => c.key === key)?.kind ?? "level";

  async function save(rows: Aim[]) {
    onChange(rows);
    setSaved("saving");
    await api.saveTargeted(id, rows);
    setSaved("done");
  }

  function update(n: number, patch: Partial<Aim>) {
    const rows = aims.map((row, i) => (i === n ? { ...row, ...patch } : row));
    // Сменили пожелание — прежнее значение может быть не того вида:
    // у правил это «жёстко», у ползунков число.
    if (patch.key) {
      const kind = kindOf(patch.key);
      rows[n].value = kind === "rule" ? "hard" : 3;
    }
    if (patch.scope === "school") rows[n].who = "";
    save(rows);
  }

  function whoOptions(scope: string): string[] {
    if (scope === "class") return classes;
    if (scope === "teacher") return teachers;
    if (scope === "parallel") return parallels;
    return [];
  }

  return (
    <div className="mt-8">
      <h2 className="text-lg font-semibold">Пожелания по адресу</h2>
      <p className="mt-1 max-w-3xl text-pencil">
        То же, что ползунки выше, но не на всю школу сразу. Правило для класса сильнее
        правила для его параллели, а оно — сильнее общего. Так «ровные дни жёстко»
        достаётся одиннадцатым, которым это по силам, и не мешает шестым.
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
                    {SCOPES.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
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
                          onChange={(e) => update(n, { key: e.target.value })}>
                    {choices.map((c) => <option key={c.key} value={c.key}>{c.title}</option>)}
                  </select>
                </td>
                <td className="pr-2">
                  {kindOf(row.key) === "rule" ? (
                    <select className={field} value={String(row.value)}
                            onChange={(e) => update(n, { value: e.target.value })}>
                      {STRICT.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
                    </select>
                  ) : (
                    <select className={field} value={Number(row.value)}
                            onChange={(e) => update(n, { value: Number(e.target.value) })}>
                      {LEVELS.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
                    </select>
                  )}
                </td>
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

      <div className="mt-3 flex items-center gap-3">
        <Button onClick={() => save([...aims, {
          scope: "parallel", who: parallels.at(-1) ?? "", key: choices[0]?.key ?? "even_days",
          value: kindOf(choices[0]?.key ?? "") === "rule" ? "hard" : 3,
        }])}>Добавить пожелание</Button>
        {saved === "saving" && <span className="text-pencil">сохраняю…</span>}
        {saved === "done" && <span className="text-pencil">сохранено</span>}
      </div>
    </div>
  );
}
