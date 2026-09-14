import { useEffect, useState } from "react";

import { api } from "../../api";
import { Button, Field, Notice, inputClass } from "../../ui";
import { DataTable, type Row } from "../../ui/DataTable";
import type { StepProps } from "./DataPage";

// «1 класс», «3 класса», «5 классов».
const plural = (n: number, one: string, few: string, many: string) => {
  const d = n % 10, h = n % 100;
  return d === 1 && h !== 11 ? one : d >= 2 && d <= 4 && (h < 12 || h > 14) ? few : many;
};

const names = (rows: Row[] | undefined, key: string) =>
  (rows ?? []).map((r) => String(r[key] ?? "").trim()).filter(Boolean);

// ------------------------------------------------------------------ школа

export function SchoolStep({ doc, update }: StepProps) {
  const s = doc.settings;
  const set = (key: string, value: unknown) => update((d) => ({ ...d, settings: { ...d.settings, [key]: value } }));
  return (
    <div className="grid max-w-2xl gap-5">
      <Field label="Название школы" hint="Попадёт в заголовок расписания и в Excel.">
        <input className={inputClass} value={String(s.name ?? "")} placeholder="Средняя школа № 1 г. Барановичи"
               onChange={(e) => set("name", e.target.value)} />
      </Field>
      <div className="grid gap-5 sm:grid-cols-2">
        <Field label="Максимум уроков в день"
               hint="Высота сетки. Уроков будет ровно столько, сколько в нагрузке.">
          <input type="number" min={4} max={10} className={inputClass} value={Number(s.periods ?? 8)}
                 onChange={(e) => set("periods", Number(e.target.value))} />
        </Field>
        <Field label="Дней с уроками" hint="В Беларуси учебная неделя пятидневная (п. 87 СанПиН № 206).">
          <select className={inputClass} value={Number(s.days ?? 5)} onChange={(e) => set("days", Number(e.target.value))}>
            {[4, 5, 6].map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </Field>
      </div>
      <label className="flex items-start gap-2">
        <input type="checkbox" className="mt-1 h-4 w-4 accent-pen" checked={Boolean(s.sixth_day ?? true)}
               onChange={(e) => set("sixth_day", e.target.checked)} />
        <span>Шестой школьный день: суббота с факультативами и кружками, уроков нет</span>
      </label>
    </div>
  );
}

// ------------------------------------------------------------------ классы

const PARALLELS = [5, 6, 7, 8, 9, 10, 11];

export function ClassesStep({ schoolId, doc, setRows, run }: StepProps) {
  const rows = doc.tables.classes ?? [];
  const [counts, setCounts] = useState<Record<number, number>>({});
  const [sizes, setSizes] = useState<Record<number, number>>({});
  const total = Object.values(counts).reduce((a, b) => a + (b || 0), 0);

  return (
    <div className="space-y-8">
      {rows.length === 0 && (
        <div>
          <p className="font-medium">Сколько классов в каждой параллели</p>
          <p className="mt-1 text-small text-pencil">
            Верхнее поле — сколько классов в параллели, нижнее — сколько в них учеников. Литеры А, Б, В проставятся сами.
          </p>
          <div className="mt-3 grid grid-cols-4 gap-3 sm:grid-cols-7">
            {PARALLELS.map((p) => (
              <div key={p}>
                <p className="mb-1 text-small font-semibold">{p}-е</p>
                <input type="number" min={0} max={10} aria-label={`Классов в ${p}-й параллели`} className={inputClass}
                       value={counts[p] ?? ""} placeholder="0"
                       onChange={(e) => setCounts({ ...counts, [p]: Number(e.target.value) })} />
                <input type="number" min={0} max={40} aria-label={`Учеников в классах ${p}-й параллели`}
                       className={`${inputClass} mt-2`} value={sizes[p] ?? ""} placeholder="24"
                       onChange={(e) => setSizes({ ...sizes, [p]: Number(e.target.value) })} />
              </div>
            ))}
          </div>
          <Button variant="primary" className="mt-4" disabled={!total}
                  onClick={() => run(() => api.generateClasses(schoolId, counts, sizes))}>
            {total ? `Завести ${total} ${plural(total, "класс", "класса", "классов")}` : "Завести классы"}
          </Button>
        </div>
      )}
      <div>
        {rows.length === 0 && <p className="mb-3 font-medium">Или по одному</p>}
        <DataTable rows={rows} onChange={(r) => setRows("classes", r)} addLabel="Добавить класс" columns={[
          { key: "класс", label: "Класс", placeholder: "7Б" },
          { key: "учеников", label: "Учеников", type: "number", width: "w-32" },
          { key: "повышенный уровень", label: "Повышенный уровень", type: "bool", width: "w-44",
            title: "Проставляется сам, если в нагрузке у предмета выбран повышенный уровень." },
        ]} />
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ кабинеты

const SPECIAL = ["физика", "химия", "биология", "компьютерный", "спортзал",
                 "мастерская (техтруд)", "мастерская (обсл. труд)", "актовый зал"];

export function RoomsStep({ schoolId, doc, input, setRows, run }: StepProps) {
  const rows = doc.tables.rooms ?? [];
  const classes = (doc.tables.classes ?? []).length;
  const [regular, setRegular] = useState<number>();
  const [special, setSpecial] = useState<Record<string, number>>({});
  const [suggested, setSuggested] = useState(false);
  const [suggestFailed, setSuggestFailed] = useState(false);
  const kinds = [...new Set([...SPECIAL, ...Object.keys(special)])]
    .filter((k) => k !== "обычный" && input.options.room_kinds.includes(k));

  // Числа — не «по одному на глаз», а посчитанные по классам и типовому плану
  // (server/entry.py rooms_suggest): иначе путь «жму по порядку» собирал школу,
  // где труду и информатике не хватает кабинетов, и узнавалось это только в конце.
  useEffect(() => {
    if (rows.length) return;
    api.roomsSuggest(schoolId).then((s) => {
      setRegular(s.regular);
      setSpecial(s.special);
      setSuggested(true);
    }).catch(() => setSuggestFailed(true));
  }, [schoolId, rows.length]);

  return (
    <div className="space-y-8">
      {input.rooms_verdict.map((line) => (
        <Notice key={line} tone="no" title="Кабинетов не хватает">{line}</Notice>
      ))}
      {rows.length === 0 && (
        <div>
          <p className="font-medium">Сколько кабинетов какого типа</p>
          {suggested && (
            <p className="mt-1 max-w-prose text-small text-pencil">
              Числа посчитаны по вашим классам и типовому плану: столько нужно, чтобы расписание существовало.
              Если кабинетов в школе меньше — поправьте, система скажет, чего не хватит.
            </p>
          )}
          <div className="mt-3 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Field label="Обычных" hint="Не меньше, чем классов: на первом уроке заняты все сразу.">
              <input type="number" min={0} max={60} className={inputClass} value={regular ?? classes}
                     onChange={(e) => setRegular(Number(e.target.value))} />
            </Field>
            {kinds.map((k) => (
              <Field key={k} label={k[0].toUpperCase() + k.slice(1)}>
                <input type="number" min={0} max={10} className={inputClass} value={special[k] ?? 0}
                       onChange={(e) => setSpecial({ ...special, [k]: Number(e.target.value) })} />
              </Field>
            ))}
          </div>
          {/* Пока расчёт не пришёл, кнопка ждёт: иначе быстрый щелчок заводил одни
              обычные кабинеты без мастерских (поймано сквозным прогоном 14.09.2026). */}
          <Button variant="primary" className="mt-4" disabled={!suggested && !suggestFailed}
                  onClick={() => run(() => api.generateRooms(schoolId, regular ?? classes, special))}>
            {suggested || suggestFailed ? "Завести кабинеты" : "Считаю, сколько нужно кабинетов…"}
          </Button>
        </div>
      )}
      <DataTable rows={rows} onChange={(r) => setRows("rooms", r)} addLabel="Добавить кабинет" columns={[
        { key: "кабинет", label: "Кабинет", placeholder: "214" },
        { key: "тип", label: "Тип", type: "select", options: input.options.room_kinds },
        { key: "мест", label: "Мест", type: "number", width: "w-28" },
        { key: "классов сразу", label: "Классов сразу", type: "number", width: "w-36",
          title: "Сколько классов занимается здесь одновременно. Спортзал — обычно 2, обычный кабинет — 1." },
      ]} />
    </div>
  );
}

// ------------------------------------------------------------------ предметы

export function SubjectsStep({ schoolId, doc, input, setRows, run }: StepProps) {
  const rows = doc.tables.subjects ?? [];
  const [message, setMessage] = useState<string>();
  return (
    <div className="space-y-6">
      <div>
        <Button variant={rows.length ? "quiet" : "primary"} onClick={async () => {
          const r = await run(() => api.subjectsFromPlan(schoolId));
          if (r) setMessage(r.added ? `Добавлено предметов: ${r.added}.` : "Все предметы типового плана уже заведены.");
        }}>
          Взять предметы из типового плана
        </Button>
        {message && <p className="mt-2 text-small text-pencil" aria-live="polite">{message}</p>}
      </div>
      <p className="max-w-prose text-small text-pencil">
        Предмету, которому нужен особый кабинет, выберите тип. «Только в нём» — для тех, кого без своего
        кабинета не провести: физкультура, информатика, труд.
      </p>
      <DataTable rows={rows} onChange={(r) => setRows("subjects", r)} addLabel="Добавить предмет" columns={[
        { key: "предмет", label: "Предмет" },
        { key: "кабинет", label: "Кабинет", type: "select", options: input.options.room_kinds },
        { key: "только в нём", label: "Только в нём", type: "bool", width: "w-32",
          title: "Урок нельзя провести нигде, кроме кабинета этого типа." },
        { key: "всегда парой", label: "Всегда парой", type: "bool", width: "w-32",
          title: "Ставится только двумя уроками подряд — так обычно идёт трудовое обучение." },
      ]} />
    </div>
  );
}

// ------------------------------------------------------------------ учителя

const METHOD_DAY = { "": "нет", "1": "Пн", "2": "Вт", "3": "Ср", "4": "Чт", "5": "Пт" };

export function TeachersStep({ doc, setRows }: StepProps) {
  const rows = doc.tables.teachers ?? [];
  const [pasted, setPasted] = useState("");
  const have = new Set(names(rows, "ФИО"));
  const fresh = [...new Set(pasted.split("\n").map((s) => s.trim()).filter((s) => s && !have.has(s)))];

  return (
    <div className="space-y-8">
      {/* Пятьдесят фамилий по одной — полчаса. Список обычно уже есть
          в Excel: столбец копируется и вставляется сюда целиком. */}
      <details open={rows.length === 0} className="rounded-lg border border-rule bg-sheet p-4">
        <summary className="cursor-pointer font-medium">Вставить списком из Excel</summary>
        <textarea className={`${inputClass} mt-3 h-40 font-sans`} value={pasted}
                  placeholder={"Иванова Ирина Ивановна\nПетров Пётр Петрович"}
                  onChange={(e) => setPasted(e.target.value)} />
        <p className="mt-1 text-small text-pencil">По одному учителю на строку. Уже заведённые пропустятся.</p>
        <Button variant={rows.length ? "quiet" : "primary"} className="mt-3" disabled={!fresh.length}
                onClick={() => {
                  setRows("teachers", [...rows, ...fresh.map((name) => ({
                    "ФИО": name, "методический день": "", "свой кабинет": "—", "уроков в день": "", "совместитель": false,
                  }))]);
                  setPasted("");
                }}>
          {fresh.length ? `Добавить учителей: ${fresh.length}` : "Добавить учителей"}
        </Button>
      </details>
      <DataTable rows={rows} onChange={(r) => setRows("teachers", r)} addLabel="Добавить учителя" columns={[
        { key: "ФИО", label: "ФИО", placeholder: "Иванова И. И." },
        { key: "методический день", label: "Методический день", type: "select", width: "w-40",
          options: Object.keys(METHOD_DAY), labels: METHOD_DAY },
        { key: "свой кабинет", label: "Свой кабинет", type: "select", width: "w-40",
          options: ["—", ...names(doc.tables.rooms, "кабинет")],
          title: "При кабинетной системе уроки учителя ставятся в его кабинет." },
        { key: "уроков в день", label: "Уроков в день", width: "w-32",
          title: "Потолок: больше уроков в один день не поставится. Пусто — без ограничения." },
        { key: "совместитель", label: "Совместитель", type: "bool", width: "w-32",
          title: "Работает ещё в одной школе. Дни, когда его у нас нет, отметьте в пожеланиях." },
      ]} />
    </div>
  );
}
