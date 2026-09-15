import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api, type Directory } from "./api";
import { cx } from "./ui";

type Item = { group: string; label: string; hint?: string; to: string };

// Быстрый переход по ⌘K: раздел, класс или учитель. Сетка на 24 класса
// не помещается на экран, и найти «7Б» или «Иванюк» прокруткой долго.
// Класс и учитель открываются на экране расписания через адрес
// (?class= / ?teacher=) — там колонка прокручивается, учитель подсвечивается.
export function CommandPalette({ id, open, onClose }: { id: string; open: boolean; onClose: () => void }) {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const [dir, setDir] = useState<Directory | null>(null);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(false);
  // Enter, нажатый раньше, чем пришли классы и учителя: завуч печатает «7б»
  // и жмёт Enter быстрее, чем отвечает сервер, — переход случится по приходу.
  const pendingEnter = useRef(false);
  const input = useRef<HTMLInputElement>(null);
  const list = useRef<HTMLUListElement>(null);

  useEffect(() => {
    // Строка очищается при ЗАКРЫТИИ, а не при открытии: сброс при открытии
    // приходит позже первых нажатий, и «Иванюк» дописывался к прошлому «7б»
    // (найдено сквозным прогоном 15.09.2026).
    if (!open) {
      setQuery("");
      setActive(0);
      return;
    }
    input.current?.focus();
    pendingEnter.current = false;
    setLoading(true);
    api.latest(id)
      .then((s) => {
        setDir(s.directory);
        const byTeacher: Record<string, number> = {};
        for (const l of s.lessons) byTeacher[l.teacher_id] = (byTeacher[l.teacher_id] ?? 0) + 1;
        setCounts(byTeacher);
      })
      .catch(() => setDir(null))
      .finally(() => setLoading(false));
  }, [open, id]);

  const items = useMemo<Item[]>(() => {
    const pages: Item[] = [
      { group: "Разделы", label: "Данные", to: `/s/${id}/data` },
      { group: "Разделы", label: "Составление", to: `/s/${id}` },
      { group: "Разделы", label: "Расписание", to: `/s/${id}/schedule` },
      { group: "Разделы", label: "Что если", to: `/s/${id}/whatif` },
      { group: "Разделы", label: "Замены", to: `/s/${id}/substitutions` },
      { group: "Разделы", label: "Печать", to: `/s/${id}/print` },
    ];
    if (!dir) return pages;
    return [
      ...pages,
      ...dir.classes.map((c) => ({ group: "Классы", label: c.name, to: `/s/${id}/schedule?class=${c.id}` })),
      ...Object.entries(dir.teachers)
        .sort(([, a], [, b]) => a.localeCompare(b, "ru"))
        .map(([tid, name]) => ({ group: "Учителя", label: name, hint: `${counts[tid] ?? 0} уроков в неделю`,
                                 to: `/s/${id}/schedule?teacher=${tid}` })),
    ];
  }, [dir, counts, id]);

  // «5 а», «5А», «иван» — без регистра и пробелов; совпадение с начала выше.
  const norm = (s: string) => s.toLowerCase().replace(/\s+/g, "").replace(/ё/g, "е");
  const found = useMemo(() => {
    const q = norm(query);
    if (!q) return items.filter((i) => i.group === "Разделы");
    return items
      .filter((i) => norm(i.label).includes(q))
      .sort((a, b) => Number(!norm(a.label).startsWith(q)) - Number(!norm(b.label).startsWith(q)))
      .slice(0, 30);
  }, [items, query]);

  useEffect(() => setActive(0), [query]);
  useEffect(() => {
    list.current?.querySelector(`[data-index="${active}"]`)?.scrollIntoView({ block: "nearest" });
  }, [active]);

  function go(item: Item | undefined) {
    if (!item) return;
    pendingEnter.current = false;
    onClose();
    navigate(item.to);
  }

  useEffect(() => {
    if (open && !loading && pendingEnter.current) go(found[0]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 bg-ink/30 px-4 print:hidden" onMouseDown={onClose}>
      <div role="dialog" aria-modal="true" aria-label="Поиск"
           className="mx-auto mt-[12vh] max-w-lg overflow-hidden rounded-lg bg-sheet shadow-pop"
           onMouseDown={(e) => e.stopPropagation()}>
        <input ref={input} value={query} onChange={(e) => setQuery(e.target.value)}
               placeholder="Класс, учитель или раздел"
               className="w-full border-b border-rule bg-sheet px-4 py-3 text-heading font-normal outline-none"
               onKeyDown={(e) => {
                 if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(found.length - 1, a + 1)); }
                 if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(0, a - 1)); }
                 if (e.key === "Enter") {
                   e.preventDefault();
                   if (loading && query && !found.some((i) => i.group !== "Разделы")) pendingEnter.current = true;
                   else go(found[active]);
                 }
                 if (e.key === "Escape") { e.preventDefault(); onClose(); }
               }} />
        <ul ref={list} role="listbox" className="max-h-[50vh] overflow-auto py-1">
          {found.length === 0 && (
            <li className="px-4 py-3 text-pencil">{loading ? "Загружаю классы и учителей…" : "Ничего не нашлось."}</li>
          )}
          {found.map((item, n) => (
            <li key={item.to} data-index={n} role="option" aria-selected={n === active}>
              {(n === 0 || found[n - 1].group !== item.group) && (
                <p className="px-4 pb-1 pt-2 text-small text-pencil">{item.group}</p>
              )}
              <button type="button" onMouseMove={() => setActive(n)} onClick={() => go(item)}
                      className={cx("flex w-full items-baseline justify-between gap-3 px-4 py-2 text-left",
                                    n === active && "bg-pen-soft text-pen")}>
                <span className="font-medium">{item.label}</span>
                {item.hint && <span className="shrink-0 text-small text-pencil">{item.hint}</span>}
              </button>
            </li>
          ))}
        </ul>
        <p className="flex flex-wrap gap-x-4 gap-y-1 border-t border-rule px-4 py-2 text-small text-pencil">
          <span><Key>↑</Key> <Key>↓</Key> выбрать</span>
          <span><Key>Enter</Key> открыть</span>
          <span><Key>Esc</Key> закрыть</span>
        </p>
      </div>
    </div>
  );
}

// Клавиша-модификатор словами платформы: ⌘ на Mac, Ctrl на остальных.
export const MOD = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform) ? "⌘" : "Ctrl";

export function Key({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="rounded border border-rule bg-paper px-1.5 py-px font-sans text-small text-ink">{children}</kbd>
  );
}
