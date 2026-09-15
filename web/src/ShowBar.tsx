import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { Key } from "./CommandPalette";
import { STEPS, onShowChange, readShow, writeShow, type ShowState } from "./show";
import { cx } from "./ui";

// Полоса режима показа внизу экрана. Зал видит только «3 из 10, Составление» —
// подсказка «что сделать и что сказать» открывается по кнопке или клавише H.
// Листается кнопками и PageDown / PageUp: их шлёт кликер для презентаций.
export function ShowBar() {
  const [state, setState] = useState<ShowState | null>(readShow);
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => onShowChange(setState), []);

  // Полоса не должна закрывать низ страницы: пока показ идёт, у страницы запас снизу.
  const active = Boolean(state);
  useEffect(() => {
    document.body.style.paddingBottom = active ? "88px" : "";
    return () => { document.body.style.paddingBottom = ""; };
  }, [active]);

  const go = (step: number) => {
    if (!state) return;
    const next = Math.max(0, Math.min(STEPS.length - 1, step));
    writeShow({ ...state, step: next });
    navigate(STEPS[next].path(state.school));
  };

  useEffect(() => {
    if (!state) return;
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (target.closest?.("input, textarea, select, [role=dialog]")) return;
      if (e.key === "PageDown") { e.preventDefault(); go(state.step + 1); }
      if (e.key === "PageUp") { e.preventDefault(); go(state.step - 1); }
      if ((e.key === "h" || e.key === "р") && !e.metaKey && !e.ctrlKey && !e.altKey) {
        writeShow({ ...state, notes: !state.notes });
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state]);

  if (!state) return null;
  const step = STEPS[state.step] ?? STEPS[0];
  const onRoute = location.pathname === step.path(state.school).split("?")[0];

  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-4 z-50 flex flex-col items-center gap-2 px-4 print:hidden">
      {state.notes && (
        <div className="pointer-events-auto w-full max-w-xl rounded-lg border border-rule bg-sheet p-4 text-small shadow-pop">
          <p className="font-semibold">Сделать</p>
          <ul className="mt-1 list-disc space-y-0.5 pl-5">
            {step.todo.map((line) => <li key={line}>{line}</li>)}
          </ul>
          <p className="mt-3 font-semibold">Сказать</p>
          <p className="mt-1 text-ink/80">«{step.say}»</p>
          <p className="mt-3 text-pencil">
            Около {step.seconds} с. Весь показ — около {Math.round(STEPS.reduce((s, x) => s + x.seconds, 0) / 60)} мин.
          </p>
        </div>
      )}
      <div role="toolbar" aria-label="Режим показа"
           className="pointer-events-auto flex max-w-full flex-wrap items-center gap-x-3 gap-y-2 rounded-lg bg-ink px-3 py-2 text-small text-white shadow-pop">
        <span className="px-1 tabular-nums text-white/70">{state.step + 1} из {STEPS.length}</span>
        <span className="font-semibold">{step.title}</span>
        {!onRoute && (
          <button type="button" className="text-white/80 underline underline-offset-4 hover:text-white"
                  onClick={() => navigate(step.path(state.school))}>
            к этому шагу
          </button>
        )}
        <span className="flex gap-1.5">
          <button type="button" disabled={state.step === 0} onClick={() => go(state.step - 1)}
                  className="rounded px-2.5 py-1 hover:bg-white/10 disabled:opacity-40">Назад</button>
          <button type="button" disabled={state.step === STEPS.length - 1} onClick={() => go(state.step + 1)}
                  className="rounded bg-white px-2.5 py-1 font-medium text-ink hover:bg-white/90 disabled:opacity-40">Дальше</button>
          <button type="button" aria-pressed={state.notes} onClick={() => writeShow({ ...state, notes: !state.notes })}
                  className={cx("rounded px-2.5 py-1 hover:bg-white/10", state.notes && "bg-white/15")}>Подсказка</button>
          <button type="button" onClick={() => writeShow(null)} className="rounded px-2.5 py-1 text-white/70 hover:bg-white/10">
            Выйти
          </button>
        </span>
        <span className="hidden text-white/50 lg:inline">
          <Key>PgDn</Key> дальше, <Key>H</Key> подсказка
        </span>
      </div>
    </div>
  );
}
