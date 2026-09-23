import type { Directory, LessonDTO } from "../api";
import { cx } from "../ui";

// Сколько баллов трудности набирает каждый день каждого класса. Норма
// (п. 94 ССЭТ) хочет пик во вторник, среду или пятницу и лёгкий понедельник —
// в сетке на 24 класса этого не увидеть, а здесь видно одним взглядом.
// Интенсивность — относительно самого трудного дня ЭТОГО класса: у пятого
// и одиннадцатого классов разные суммы, сравнивать надо форму недели.
const SHADES = ["", "bg-pen/10", "bg-pen/25", "bg-pen/45", "bg-pen/70 text-white"];

export function DifficultyMap({ dir, lessons, onClass }: {
  dir: Directory;
  lessons: LessonDTO[];
  onClass: (classId: string) => void;
}) {
  // Подгруппы одного деления стоят в одном часе — предмет в часе считается один раз.
  const seen = new Set<string>();
  const sums = new Map<string, number>();
  for (const l of lessons) {
    for (const classId of dir.groups[l.group_id]?.class_ids ?? []) {
      const once = `${classId}|${l.day}|${l.period}|${l.subject_id}`;
      if (seen.has(once)) continue;
      seen.add(once);
      const key = `${classId}|${l.day}`;
      sums.set(key, (sums.get(key) ?? 0) + (dir.difficulty[classId]?.[l.subject_id] ?? 0));
    }
  }
  const dayName = (n: number) => dir.days.find((d) => d.n === n)?.name ?? String(n);
  const offPeak = dir.classes.filter((c) => {
    const values = dir.days.map((d) => sums.get(`${c.id}|${d.n}`) ?? 0);
    const peak = dir.days[values.indexOf(Math.max(...values))]?.n;
    return Math.max(...values) > 0 && !(dir.peak_days[c.id] ?? []).includes(peak);
  }).length;

  return (
    <section className="mt-5 rounded-lg border border-rule bg-sheet p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
        <p className="text-heading">Трудность по дням</p>
        <p className="text-small text-pencil">
          Сумма баллов трудности уроков за день. Чем темнее, тем тяжелее день для этого класса.
          «!» — самый трудный день не в дни пика нагрузки (п. 94 ССЭТ или выбор школы): таких классов {offPeak}.
        </p>
      </div>
      <div className="mt-3 overflow-x-auto">
        <table className="border-separate border-spacing-0.5 font-narrow text-cell">
          <thead>
            <tr>
              <th />
              {dir.classes.map((c) => (
                <th key={c.id} scope="col" className="min-w-[44px] px-1 text-center text-small font-semibold">
                  <button type="button" className="rounded px-1 hover:bg-paper" title={`Показать ${c.name} в сетке`}
                          onClick={() => onClass(c.id)}>
                    {c.name}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {dir.days.map((day) => (
              <tr key={day.n}>
                <th scope="row" className="pr-2 text-left font-normal text-pencil">{day.name.slice(0, 2)}</th>
                {dir.classes.map((c) => {
                  const values = dir.days.map((d) => sums.get(`${c.id}|${d.n}`) ?? 0);
                  const max = Math.max(...values);
                  const value = sums.get(`${c.id}|${day.n}`) ?? 0;
                  const isPeak = max > 0 && value === max;
                  const wrongPeak = isPeak && !(dir.peak_days[c.id] ?? []).includes(day.n);
                  return (
                    <td key={c.id}
                        title={`${c.name}, ${dayName(day.n)}: ${value} баллов${wrongPeak ? " — пик не в рекомендованный день" : ""}`}
                        className={cx("h-7 rounded-[3px] text-center tabular-nums",
                                      SHADES[max ? Math.round((value / max) * 4) : 0],
                                      isPeak && "font-semibold")}>
                      {value || ""}
                      {wrongPeak && <span className="ml-0.5 font-bold text-worse">!</span>}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
