"use client";

import { useMemo } from "react";
import grid from "@/data/grid.json";

type Cell = { s: string; t: string; r: string };
type Cells = Record<string, Record<string, Cell>>;

const cells = grid.cells as Cells;

/** Все занятые клетки в порядке, в котором их «ставит» солвер на экране.
 *  Порядок детерминированный: он вычисляется из самих данных, поэтому
 *  сервер и браузер рисуют одно и то же и гидрация не расходится. */
function useFillOrder() {
  return useMemo(() => {
    const keys: string[] = [];
    for (const cls of grid.classes) {
      for (let d = 1; d <= grid.days.length; d += 1) {
        for (let p = 1; p <= grid.periods; p += 1) {
          if (cells[cls]?.[`${d}-${p}`]) keys.push(`${cls}|${d}-${p}`);
        }
      }
    }
    // Солвер не заполняет сетку слева направо: он ставит уроки по всей школе
    // сразу. Перемешиваем фиксированным шагом, чтобы это было видно, но
    // результат не зависел от случайности.
    const step = 7;
    const mixed: string[] = [];
    for (let offset = 0; offset < step; offset += 1) {
      for (let i = offset; i < keys.length; i += step) mixed.push(keys[i]);
    }
    return mixed;
  }, []);
}

export function ScheduleGrid({
  progress = 1,
  compact = false,
}: {
  /** Доля поставленных уроков, 0..1. */
  progress?: number;
  /** Плотный вид для героя: уже колонки, без фамилий. */
  compact?: boolean;
}) {
  const order = useFillOrder();
  const shown = useMemo(() => {
    const count = Math.round(order.length * Math.min(Math.max(progress, 0), 1));
    return new Set(order.slice(0, count));
  }, [order, progress]);

  return (
    <div className="overflow-hidden rounded-lg border border-rule bg-sheet">
      <table className="w-full border-collapse text-[13px] leading-4 font-narrow">
        <thead>
          <tr>
            <th className="sticky left-0 z-10 w-14 border-b border-r border-rule bg-paper px-2 py-2 text-left text-[11px] font-semibold text-pencil">
              Урок
            </th>
            {grid.classes.map((cls) => (
              <th
                key={cls}
                className="border-b border-r border-rule bg-paper px-2 py-2 text-[13px] font-semibold text-ink last:border-r-0"
              >
                {cls}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {grid.days.map((day, dayIndex) => {
            const d = dayIndex + 1;
            return Array.from({ length: grid.periods }, (_, periodIndex) => {
              const p = periodIndex + 1;
              const firstOfDay = p === 1;
              return (
                <tr key={`${d}-${p}`}>
                  <th
                    scope="row"
                    className={`sticky left-0 z-10 border-r border-rule bg-paper px-2 py-1 text-left text-[11px] font-normal text-pencil ${
                      firstOfDay ? "border-t-2 border-t-rule" : "border-b border-rule"
                    }`}
                  >
                    {firstOfDay ? (
                      <span className="font-semibold text-ink">{day}</span>
                    ) : (
                      p
                    )}
                  </th>
                  {grid.classes.map((cls) => {
                    const cell = cells[cls]?.[`${d}-${p}`];
                    const visible = cell && shown.has(`${cls}|${d}-${p}`);
                    return (
                      <td
                        key={cls}
                        className={`border-r border-rule px-2 py-1 align-top last:border-r-0 ${
                          firstOfDay ? "border-t-2 border-t-rule" : "border-b border-rule"
                        }`}
                      >
                        {visible ? (
                          <span className="block">
                            <span className="block truncate font-medium text-ink">
                              {cell.s}
                            </span>
                            {!compact && (
                              <span className="block truncate text-[11px] text-pencil">
                                {cell.t}
                              </span>
                            )}
                          </span>
                        ) : (
                          <span className="block h-4" aria-hidden="true" />
                        )}
                      </td>
                    );
                  })}
                </tr>
              );
            });
          })}
        </tbody>
      </table>
    </div>
  );
}

export const gridStats = {
  classes: grid.classes.length,
  lessons: Object.values(cells).reduce((n, c) => n + Object.keys(c).length, 0),
};
