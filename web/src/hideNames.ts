import { useCallback, useEffect, useState } from "react";

// Обезличивание — общее для всего приложения, а не для одного экрана.
// Раньше «Скрыть ФИО» стояло отдельным чекбоксом на расписании, заменах и печати,
// а «Что если» и «Данные» показывали настоящие фамилии всегда. На показе третьим
// лицам и в саммари это прямое нарушение §8.4 CLAUDE.md: завуч должен уметь одним
// переключателем закрыть фамилии во всём приложении.
//
// Состояние живёт в sessionStorage: переживает переходы между разделами и
// перезагрузку, но не остаётся включённым навсегда — школе внутри себя имена нужны.
const KEY = "lad.hideNames";
const EVENT = "lad:hide-names";

function read(): boolean {
  try {
    return sessionStorage.getItem(KEY) === "1";
  } catch {
    return false; // приватное окно или заблокированное хранилище
  }
}

/** Общий переключатель «Скрыть ФИО учителей». */
export function useHideNames(): [boolean, (on: boolean) => void] {
  const [on, setOn] = useState(read);

  useEffect(() => {
    const sync = () => setOn(read());
    window.addEventListener(EVENT, sync);
    return () => window.removeEventListener(EVENT, sync);
  }, []);

  const set = useCallback((next: boolean) => {
    try {
      sessionStorage.setItem(KEY, next ? "1" : "0");
    } catch {
      /* не сохранилось — переключатель всё равно сработает в этой вкладке */
    }
    window.dispatchEvent(new Event(EVENT));
  }, []);

  return [on, set];
}

/** Номера учителей: «Учитель 1», «Учитель 2» — по порядку в справочнике. */
export function teacherNumbers(teachers: Record<string, string>): Map<string, number> {
  return new Map(Object.keys(teachers).map((id, i) => [id, i + 1]));
}

/**
 * Замена фамилий в готовом тексте. Причины отказа, блокеры «Что если» и подписи
 * приходят с сервера одной строкой — обезличить их можно только по словарю.
 * Длинные имена заменяются первыми: иначе «Иванов» съест «Иванова».
 */
export function masker(hide: boolean, teachers: Record<string, string>): (text: string) => string {
  if (!hide) return (text) => text;
  const numbers = teacherNumbers(teachers);
  const pairs = Object.entries(teachers)
    .filter(([, name]) => Boolean(name))
    .sort(([, a], [, b]) => b.length - a.length);
  return (text: string) => {
    let out = text;
    for (const [id, name] of pairs) out = out.split(name).join(`Учитель ${numbers.get(id)}`);
    return out;
  };
}

/** Имя одного учителя по его id. */
export function alias(hide: boolean, teachers: Record<string, string>, id: string): string {
  if (!hide) return teachers[id] ?? id;
  return `Учитель ${teacherNumbers(teachers).get(id) ?? "?"}`;
}
