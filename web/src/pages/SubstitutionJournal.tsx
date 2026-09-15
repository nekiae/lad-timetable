import { useState } from "react";

import type { Journal, JournalEntry } from "../api";
import { Button, Field, Panel, cx, inputClass } from "../ui";

// Журнал замен за месяц: записи по дням и итог «кто сколько заменял» — по нему
// в конце месяца считают часы замен. Удаление — в два щелчка: запись журнала
// восстановить неоткуда.
export function SubstitutionJournal({ journal, month, onMonth, shownName, opened, onOpen, onDelete, onDownload }: {
  journal: Journal | undefined;
  month: string;
  onMonth: (month: string) => void;
  shownName: (name: string) => string;
  opened: string | null;
  onOpen: (entry: JournalEntry) => void;
  onDelete: (entry: JournalEntry) => void;
  onDownload: () => void;
}) {
  const [confirm, setConfirm] = useState<string | null>(null);
  const monthName = /^\d{4}-\d{2}$/.test(month)
    ? new Date(`${month}-15T12:00:00`).toLocaleDateString("ru-RU", { month: "long", year: "numeric" }) : "";
  const dayName = (date: string) => {
    const text = new Date(`${date}T12:00:00`).toLocaleDateString("ru-RU", { weekday: "long", day: "numeric", month: "long" });
    return text.charAt(0).toUpperCase() + text.slice(1);
  };

  return (
    <section className="mt-12 max-w-5xl border-t border-rule pt-8 print:hidden">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="text-heading">Журнал замен</h2>
          <p className="mt-1 max-w-prose text-small text-pencil">
            Сохранённые замены по дням. Итог месяца — для учёта часов замен.
          </p>
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <Field label="Месяц" className="w-44">
            <input type="month" className={inputClass} value={month} onChange={(e) => onMonth(e.target.value)} />
          </Field>
          <Button disabled={!journal?.days.length} onClick={onDownload}>Скачать Excel за месяц</Button>
        </div>
      </div>

      {!journal ? (
        <p className="mt-4 text-pencil">Загружаю журнал…</p>
      ) : journal.days.length === 0 ? (
        <p className="mt-4 max-w-prose text-pencil">
          За {monthName} замен не сохранено. Подберите замены выше и нажмите «Сохранить в журнал».
        </p>
      ) : (
        <div className="mt-5 grid gap-6 lg:grid-cols-[minmax(0,1fr)_18rem]">
          <ol className="space-y-3">
            {journal.days.map((entry) => (
              <li key={entry.id}>
                <Panel as="div" className={cx(opened === entry.id && "border-pen")}>
                  <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-2">
                    <p>
                      <span className="font-semibold">{dayName(entry.date)}.</span>{" "}
                      Отсутствует: {shownName(entry.absent)}
                    </p>
                    <span className="flex shrink-0 gap-3 text-small">
                      <button type="button" className="text-pen underline-offset-4 hover:underline" onClick={() => onOpen(entry)}>
                        Открыть
                      </button>
                      {confirm === entry.id ? (
                        <>
                          <button type="button" className="font-medium text-no underline-offset-4 hover:underline"
                                  onClick={() => { setConfirm(null); onDelete(entry); }}>
                            Да, удалить
                          </button>
                          <button type="button" className="text-pencil underline-offset-4 hover:underline" onClick={() => setConfirm(null)}>
                            Отмена
                          </button>
                        </>
                      ) : (
                        <button type="button" className="text-pencil underline-offset-4 hover:underline" onClick={() => setConfirm(entry.id)}>
                          Удалить
                        </button>
                      )}
                    </span>
                  </div>
                  <ul className="mt-2 space-y-0.5 text-small">
                    {[...entry.rows].sort((a, b) => a.period - b.period).map((row) => (
                      <li key={`${row.period}-${row.group}-${row.subject}`}>
                        {row.period}-й урок, {row.group}, {row.subject}:{" "}
                        <span className={row.substitute ? "font-medium" : "text-pencil"}>
                          {row.substitute ? shownName(row.substitute) : "урок не проводится"}
                        </span>
                      </li>
                    ))}
                  </ul>
                </Panel>
              </li>
            ))}
          </ol>

          <Panel as="div" className="h-fit text-small">
            <p className="text-heading">Итог за {monthName}</p>
            <p className="mt-1">
              Проведено замен: <span className="font-semibold">{journal.total}</span>. Не проводилось уроков:{" "}
              {journal.not_held}.
            </p>
            {journal.by_substitute.length > 0 && (
              <table className="mt-3 w-full border-collapse">
                <thead>
                  <tr className="border-b border-ink/30 text-left">
                    <th className="py-1.5 font-semibold">Кто заменял</th>
                    <th className="py-1.5 text-right font-semibold">Уроков</th>
                  </tr>
                </thead>
                <tbody>
                  {journal.by_substitute.map((x) => (
                    <tr key={x.name} className="border-b border-rule">
                      <td className="py-1.5">{shownName(x.name)}</td>
                      <td className="py-1.5 text-right tabular-nums">{x.lessons}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Panel>
        </div>
      )}
    </section>
  );
}
