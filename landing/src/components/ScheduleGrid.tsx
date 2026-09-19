"use client";

import { useMemo, useState } from "react";
import grid from "@/data/grid.json";

type Cell = { s: string; t: string; r: string };
type Cells = Record<string, Record<string, Cell>>;

const cells = grid.cells as Cells;

/** Сколько классов видно на узком экране. Шесть колонок в 375px превращаются
 *  в нечитаемую кашу, поэтому на телефоне показываем первые три, а остальные
 *  прячем через CSS. Скрытые колонки остаются в разметке: класть сетку в
 *  горизонтальный скролл нельзя, он на телефоне ворует вертикальный свайп. */
const MOBILE_CLASSES = 3;

/** Седьмой урок занят только в трёх клетках из всей недели и во всех классах,
 *  которые видно на телефоне, пуст. Пять пустых строк там не нужны. */
const MOBILE_PERIODS = 6;

/** Все занятые клетки в порядке, в котором их «ставит» солвер на экране.
 *  Порядок детерминированный: он вычисляется из самих данных, поэтому
 *  сервер и браузер рисуют одно и то же и гидрация не расходится. */
const fillOrder = (() => {
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
})();

/** Откуда прилетает клетка. Значения выводятся из её ключа, поэтому одинаковы
 *  на сервере и в браузере и не дёргаются между рендерами. */
function scatter(key: string): React.CSSProperties {
  let h = 0;
  for (let i = 0; i < key.length; i += 1) h = (h * 31 + key.charCodeAt(i)) % 997;
  const dx = ((h % 17) - 8) * 7;
  const dy = (((h >> 3) % 13) - 6) * 9;
  const rot = (((h >> 5) % 11) - 5) * 1.6;
  return {
    "--dx": `${dx}px`,
    "--dy": `${dy}px`,
    "--rot": `${rot}deg`,
    "--delay": `${(h % 22) * 38}ms`,
  } as React.CSSProperties;
}

function columnVisibility(index: number) {
  return index < MOBILE_CLASSES ? "" : "hidden sm:table-cell";
}

function rowVisibility(period: number) {
  return period <= MOBILE_PERIODS ? "" : "hidden sm:table-row";
}

export function ScheduleGrid({
  progress = 1,
  compact = false,
  settle = false,
  interactive = false,
}: {
  /** Доля поставленных уроков, 0..1. */
  progress?: number;
  /** Плотный вид для героя: без фамилий учителей. */
  compact?: boolean;
  /** Уроки влетают из беспорядка и встают на места. Для героя. */
  settle?: boolean;
  /** Клетку можно выбрать, под сеткой появляется учитель и кабинет. */
  interactive?: boolean;
}) {
  const shown = useMemo(() => {
    const count = Math.round(
      fillOrder.length * Math.min(Math.max(progress, 0), 1),
    );
    return new Set(fillOrder.slice(0, count));
  }, [progress]);

  const [picked, setPicked] = useState<string | null>(null);

  const pickedCell = picked
    ? cells[picked.split("|")[0]]?.[picked.split("|")[1]]
    : null;

  return (
    <div>
      <div className="overflow-hidden rounded-lg border border-rule bg-sheet">
        <table className="w-full table-fixed border-collapse font-narrow text-[11px] leading-[14px] sm:text-[13px] sm:leading-4">
          <colgroup>
            <col className="w-9 sm:w-14" />
            {grid.classes.map((cls, i) => (
              <col key={cls} className={columnVisibility(i)} />
            ))}
          </colgroup>
          <thead>
            <tr>
              <th className="border-b border-r border-rule bg-paper px-1.5 py-2 text-left text-[10px] font-semibold text-pencil sm:px-2 sm:text-[11px]">
                Урок
              </th>
              {grid.classes.map((cls, i) => (
                <th
                  key={cls}
                  className={`border-b border-r border-rule bg-paper px-1.5 py-2 text-[12px] font-semibold text-ink last:border-r-0 sm:px-2 sm:text-[13px] ${columnVisibility(
                    i,
                  )}`}
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
                // Граница снизу нужна у каждой строки, иначе первый урок дня
                // визуально слипается со вторым.
                const rowEdge = `border-b border-rule ${
                  firstOfDay ? "border-t-2 border-t-rule" : ""
                }`;
                return (
                  <tr key={`${d}-${p}`} className={rowVisibility(p)}>
                    <th
                      scope="row"
                      className={`border-r border-rule bg-paper px-1.5 py-1 text-left text-[10px] font-normal text-pencil sm:px-2 sm:text-[11px] ${rowEdge}`}
                    >
                      {firstOfDay ? (
                        <span className="font-semibold text-ink">{day}</span>
                      ) : (
                        p
                      )}
                    </th>
                    {grid.classes.map((cls, i) => {
                      const key = `${cls}|${d}-${p}`;
                      const cell = cells[cls]?.[`${d}-${p}`];
                      const visible = cell && shown.has(key);
                      const isPicked = interactive && picked === key;
                      return (
                        <td
                          key={cls}
                          onClick={
                            interactive && visible
                              ? () => setPicked(isPicked ? null : key)
                              : undefined
                          }
                          onMouseEnter={
                            interactive && visible
                              ? () => setPicked(key)
                              : undefined
                          }
                          className={`border-r border-rule px-1.5 py-1 align-top last:border-r-0 sm:px-2 ${rowEdge} ${columnVisibility(
                            i,
                          )} ${
                            interactive && visible ? "cursor-pointer" : ""
                          } ${isPicked ? "bg-pen-soft" : ""}`}
                        >
                          {visible ? (
                            <span
                              className={`block ${settle ? "settle" : ""}`}
                              style={settle ? scatter(key) : undefined}
                            >
                              <span
                                className={`block truncate font-medium ${
                                  isPicked ? "text-pen" : "text-ink"
                                }`}
                              >
                                {cell.s}
                              </span>
                              {!compact && (
                                <span className="hidden truncate text-[11px] text-pencil sm:block">
                                  {cell.t}
                                </span>
                              )}
                            </span>
                          ) : (
                            <span
                              className="block h-3.5 sm:h-4"
                              aria-hidden="true"
                            />
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

      {interactive && (
        // Место под подпись занято всегда: иначе страница дёргается на каждом
        // касании клетки.
        <p className="mt-3 min-h-[40px] text-[13px] leading-5 text-pencil">
          {pickedCell && picked ? (
            <>
              <span className="font-medium text-ink">
                {picked.split("|")[0]}, {pickedCell.s}
              </span>
              <br />
              {pickedCell.t}, кабинет {pickedCell.r}
            </>
          ) : (
            "Нажмите на урок, чтобы увидеть учителя и кабинет."
          )}
        </p>
      )}
    </div>
  );
}

export const gridStats = {
  classes: grid.classes.length,
  lessons: Object.values(cells).reduce((n, c) => n + Object.keys(c).length, 0),
};
