import { Button, cx } from ".";

export type Row = Record<string, unknown>;

export type Column = {
  key: string;
  label: string;
  type?: "text" | "number" | "bool" | "select";
  options?: string[];
  labels?: Record<string, string>; // подписи вариантов, если хранится код («1» → «Пн»)
  placeholder?: string;
  title?: string; // пояснение к колонке — во всплывающей подсказке заголовка
  width?: string;
};

// Поле без рамки: таблица читается как таблица, а не как стена полей.
// Рамка появляется при наведении, синяя — при фокусе.
const field =
  "w-full min-w-0 rounded border border-transparent bg-transparent px-2 py-1.5 " +
  "hover:border-rule focus:border-pen focus:bg-sheet focus:outline-none";

function Cell({ column, value, onChange }: {
  column: Column; value: unknown; onChange: (value: unknown) => void;
}) {
  if (column.type === "bool")
    return <input type="checkbox" aria-label={column.label} className="ml-2 h-4 w-4 accent-pen"
                  checked={Boolean(value)} onChange={(e) => onChange(e.target.checked)} />;
  const text = value === null || value === undefined ? "" : String(value);
  if (column.type === "select") {
    const options = column.options ?? [];
    return (
      <select aria-label={column.label} className={field} value={text} onChange={(e) => onChange(e.target.value)}>
        {!options.includes(text) && <option value={text}>{column.labels?.[text] ?? text}</option>}
        {options.map((o) => <option key={o} value={o}>{column.labels?.[o] ?? o}</option>)}
      </select>
    );
  }
  if (column.type === "number")
    return <input type="number" inputMode="numeric" aria-label={column.label} className={field} value={text}
                  onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))} />;
  return <input aria-label={column.label} className={field} value={text} placeholder={column.placeholder}
                onChange={(e) => onChange(e.target.value)} />;
}

function blankRow(columns: Column[]): Row {
  return Object.fromEntries(columns.map((c) => [
    c.key, c.type === "bool" ? false : c.type === "number" ? null : c.type === "select" ? (c.options?.[0] ?? "") : "",
  ]));
}

// Таблица ввода: классы, предметы, учителя, кабинеты, нагрузка.
// Меняет строки целиком и отдаёт наверх — сохранение решает страница.
export function DataTable({ columns, rows, onChange, addLabel = "Добавить строку" }: {
  columns: Column[]; rows: Row[]; onChange: (rows: Row[]) => void; addLabel?: string;
}) {
  const set = (index: number, key: string, value: unknown) =>
    onChange(rows.map((row, n) => (n === index ? { ...row, [key]: value } : row)));

  return (
    <div>
      {rows.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-rule bg-sheet">
          <table className="w-full border-collapse text-small">
            <thead>
              <tr className="bg-paper text-left">
                <th className="w-10 border-b border-rule px-3 py-2 font-normal text-pencil">№</th>
                {columns.map((c) => (
                  <th key={c.key} title={c.title}
                      className={cx("border-b border-rule px-3 py-2 font-semibold", c.width,
                                    c.title && "cursor-help underline decoration-rule decoration-dotted underline-offset-4")}>
                    {c.label}
                  </th>
                ))}
                <th className="w-20 border-b border-rule" />
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr key={i} className="group border-b border-rule last:border-b-0">
                  <td className="px-3 text-pencil">{i + 1}</td>
                  {columns.map((c) => (
                    <td key={c.key} className="px-1 py-0.5">
                      <Cell column={c} value={row[c.key]} onChange={(v) => set(i, c.key, v)} />
                    </td>
                  ))}
                  <td className="px-2 text-right">
                    <button type="button" onClick={() => onChange(rows.filter((_, n) => n !== i))}
                            className="rounded px-2 py-1 text-pencil opacity-0 transition-opacity duration-150 hover:text-ink focus:opacity-100 group-hover:opacity-100 max-md:opacity-100">
                      Убрать
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Button className="mt-3" onClick={() => onChange([...rows, blankRow(columns)])}>{addLabel}</Button>
    </div>
  );
}
