import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Link } from "react-router-dom";

// Кирпичи интерфейса. Правила применения — docs/DESIGN.md §7.
// Страница собирается из них; новый кирпич — только когда паттерн
// встретился второй раз.

const cx = (...parts: (string | false | null | undefined)[]) => parts.filter(Boolean).join(" ");

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "quiet";
  size?: "md" | "lg";
};

// primary — одно главное действие на экран, quiet — всё остальное.
export function Button({ variant = "quiet", size = "md", className, ...rest }: ButtonProps) {
  return (
    <button
      type="button"
      {...rest}
      className={cx(
        "inline-flex items-center justify-center gap-2 rounded font-medium transition-colors duration-150",
        "disabled:cursor-not-allowed disabled:opacity-50",
        size === "lg" ? "px-6 py-3" : "px-4 py-2",
        variant === "primary"
          ? "bg-pen text-white enabled:hover:bg-pen-strong"
          : "border border-rule bg-sheet text-ink enabled:hover:border-pencil",
        className,
      )}
    />
  );
}

export function ButtonLink({ to, children, variant = "quiet" }: {
  to: string; children: ReactNode; variant?: "primary" | "quiet";
}) {
  return (
    <Link
      to={to}
      className={cx(
        "inline-flex items-center justify-center rounded px-4 py-2 font-medium transition-colors duration-150",
        variant === "primary" ? "bg-pen text-white hover:bg-pen-strong" : "border border-rule bg-sheet hover:border-pencil",
      )}>
      {children}
    </Link>
  );
}

// Белый лист, на котором лежат данные. Панель в панель не кладём.
export function Panel({ children, className, as: Tag = "section" }: {
  children: ReactNode; className?: string; as?: "section" | "div" | "aside";
}) {
  return <Tag className={cx("rounded-lg border border-rule bg-sheet p-4", className)}>{children}</Tag>;
}

const NOTICE_TONE = {
  no: "border-no/40 bg-no-soft",
  worse: "border-worse/30 bg-worse-soft",
  ok: "border-ok/30 bg-ok-soft",
  info: "border-rule bg-sheet",
};

// Сообщение о состоянии: заголовок — что случилось, текст — что делать.
export function Notice({ tone, title, children, className }: {
  tone: keyof typeof NOTICE_TONE; title?: ReactNode; children?: ReactNode; className?: string;
}) {
  return (
    <div role={tone === "no" ? "alert" : undefined}
         className={cx("rounded-lg border px-4 py-3", NOTICE_TONE[tone], className)}>
      {title && <p className={cx("font-semibold", tone === "no" && "text-no")}>{title}</p>}
      {children && <div className={cx("text-small", Boolean(title) && "mt-1")}>{children}</div>}
    </div>
  );
}

// Выбор одного варианта, когда каждому нужно пояснение.
export function Choice<T extends string>({ name, legend, value, options, onChange }: {
  name: string;
  legend: string;
  value: T;
  options: { value: T; label: string; about?: string }[];
  onChange: (value: T) => void;
}) {
  return (
    <fieldset>
      <legend className="mb-2 text-heading">{legend}</legend>
      <div className="space-y-2">
        {options.map((o) => (
          <label key={o.value}
                 className={cx(
                   "block cursor-pointer rounded border px-3 py-2 transition-colors duration-150",
                   "has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-pen",
                   value === o.value ? "border-pen bg-pen-soft" : "border-rule bg-sheet hover:border-pencil",
                 )}>
            <input type="radio" name={name} className="sr-only" checked={value === o.value}
                   onChange={() => onChange(o.value)} />
            <span className="font-medium">{o.label}</span>
            {o.about && <span className="mt-0.5 block text-small text-pencil">{o.about}</span>}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

// Выбор одного из 2–4 коротких значений.
export function Segmented<T extends string | number>({ legend, value, options, onChange }: {
  legend: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
}) {
  return (
    <fieldset>
      <legend className="mb-2 text-heading">{legend}</legend>
      <div className="inline-flex rounded border border-rule bg-sheet p-0.5">
        {options.map((o) => (
          <button key={String(o.value)} type="button" aria-pressed={value === o.value}
                  onClick={() => onChange(o.value)}
                  className={cx(
                    "rounded-[4px] px-4 py-1.5 font-medium transition-colors duration-150",
                    value === o.value ? "bg-pen text-white" : "text-ink hover:bg-paper",
                  )}>
            {o.label}
          </button>
        ))}
      </div>
    </fieldset>
  );
}

// Одна метрика. Прежнее значение зачёркнуто — видно, куда сдвинулось.
export function Stat({ label, value, was }: { label: string; value: ReactNode; was?: ReactNode }) {
  return (
    <div className="flex flex-col-reverse">
      <dt className="text-small text-pencil">{label}</dt>
      <dd className="text-metric">
        {was !== undefined && was !== value && (
          <s className="mr-2 text-body font-normal text-pencil">{was}</s>
        )}
        {value}
      </dd>
    </div>
  );
}

// Причины, цены и выгоды хода. Пункт нормы — серым рядом с причиной.
export function Reasons({ tone, items }: {
  tone: "no" | "worse" | "ok"; items: { text: string; source?: string | null }[];
}) {
  if (!items.length) return null;
  const color = tone === "no" ? "text-ink" : tone === "worse" ? "text-worse" : "text-ok";
  return (
    <ul className={cx("mt-2 space-y-1.5", color)}>
      {items.map((r, i) => (
        <li key={i}>
          {r.text}
          {r.source && <span className="block text-small text-pencil">{r.source}</span>}
        </li>
      ))}
    </ul>
  );
}

// Пустой экран: одна фраза и одно действие.
export function EmptyState({ text, action }: { text: string; action?: ReactNode }) {
  return (
    <div className="px-4 py-16 md:px-8">
      <p className="text-heading">{text}</p>
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export { cx };
