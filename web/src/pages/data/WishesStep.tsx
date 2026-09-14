import { useState } from "react";

import { cx, inputClass } from "../../ui";
import type { StepProps } from "./DataPage";

type Wish = { hard?: number[][]; soft?: number[][] };
type Mark = "free" | "cant" | "dislike";

const DAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб"];
// Щелчок по клетке перебирает: свободно → не может → нежелательно → свободно.
const NEXT: Record<Mark, Mark> = { free: "cant", cant: "dislike", dislike: "free" };

// Пожелания учителей кликом по неделе. Формат — как в data/school.json:
// ФИО → {hard: [[день, урок]], soft: [[день, урок]]}.
export function WishesStep({ doc, update }: StepProps) {
  const teachers = (doc.tables.teachers ?? []).map((r) => String(r["ФИО"] ?? "").trim()).filter(Boolean);
  const wishes = (doc.wishes ?? {}) as Record<string, Wish>;
  const [who, setWho] = useState(teachers[0] ?? "");
  const days = Number(doc.settings.days ?? 5);
  const periods = Number(doc.settings.periods ?? 8);

  if (!teachers.length) return null;

  const wish = wishes[who] ?? {};
  const has = (list: number[][] | undefined, d: number, p: number) => (list ?? []).some(([a, b]) => a === d && b === p);
  const mark = (d: number, p: number): Mark => (has(wish.hard, d, p) ? "cant" : has(wish.soft, d, p) ? "dislike" : "free");

  function cycle(d: number, p: number) {
    const next = NEXT[mark(d, p)];
    const drop = (list: number[][] | undefined) => (list ?? []).filter(([a, b]) => !(a === d && b === p));
    const changed: Wish = {
      hard: next === "cant" ? [...drop(wish.hard), [d, p]] : drop(wish.hard),
      soft: next === "dislike" ? [...drop(wish.soft), [d, p]] : drop(wish.soft),
    };
    update((doc) => ({ ...doc, wishes: { ...(doc.wishes ?? {}), [who]: changed } }));
  }

  const filled = Object.entries(wishes).filter(([, w]) => w.hard?.length || w.soft?.length);

  return (
    <div className="space-y-6">
      <select aria-label="Учитель" className={`${inputClass} max-w-sm`} value={who} onChange={(e) => setWho(e.target.value)}>
        {teachers.map((t) => <option key={t} value={t}>{t}</option>)}
      </select>

      <div className="max-w-prose space-y-1 text-small">
        <p><span className="rounded bg-no-soft px-1.5 py-0.5 font-medium text-no">не может</span> — урок сюда не встанет никогда.</p>
        <p><span className="rounded bg-worse-soft px-1.5 py-0.5 font-medium text-worse">нежелательно</span> — поставится, только если иначе расписание не сходится.</p>
        <p className="text-pencil">Всё обсуждаемое лучше отмечать как «нежелательно»: при большом числе запретов расписания может не существовать вовсе.</p>
      </div>

      <div className="overflow-x-auto">
        <table className="border-separate border-spacing-1 text-small">
          <thead>
            <tr>
              <th />
              {Array.from({ length: periods }, (_, p) => (
                <th key={p} className="w-20 font-normal text-pencil">{p + 1} урок</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {Array.from({ length: days }, (_, d) => (
              <tr key={d}>
                <th scope="row" className="pr-2 text-left font-semibold">{DAYS[d]}</th>
                {Array.from({ length: periods }, (_, p) => {
                  const m = mark(d + 1, p + 1);
                  return (
                    <td key={p}>
                      <button type="button" onClick={() => cycle(d + 1, p + 1)}
                              aria-label={`${DAYS[d]}, ${p + 1} урок: ${m === "cant" ? "не может" : m === "dislike" ? "нежелательно" : "свободно"}`}
                              className={cx("h-10 w-20 rounded border text-[12px] transition-colors duration-150",
                                            m === "cant" ? "border-no/40 bg-no-soft text-no"
                                              : m === "dislike" ? "border-worse/40 bg-worse-soft text-worse"
                                                : "border-rule bg-sheet text-pencil hover:border-pen")}>
                        {m === "cant" ? "не может" : m === "dislike" ? "нежелательно" : ""}
                      </button>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {filled.length > 0 && (
        <p className="text-small text-pencil">
          Заполнено у {filled.length}: {filled.map(([name, w]) =>
            `${name} (${w.hard?.length ?? 0} запретов, ${w.soft?.length ?? 0} пожеланий)`).join("; ")}
        </p>
      )}
    </div>
  );
}
