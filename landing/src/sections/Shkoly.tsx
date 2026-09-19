/** Цифры из out/demo/*_report.json, посчитаны валидатором проекта.
 *  Все четыре школы - модели по открытым данным, а не выгрузки из
 *  работающих школ. Так и написано под таблицей. */
const schools = [
  { name: "Сельская школа", classes: 7, lessons: 236, windows: 0, violations: 0 },
  { name: "Школа райцентра", classes: 14, lessons: 490, windows: 0, violations: 0 },
  { name: "Школа агрогородка", classes: 24, lessons: 838, windows: 0, violations: 25 },
  { name: "Городская гимназия", classes: 28, lessons: 980, windows: 0, violations: 3 },
];

/** Короткая подпись — для карточек на телефоне: в две строки подписи
 *  разъезжаются и цифры перестают стоять на одной линии. */
const columns = [
  { key: "classes", label: "Классов", short: "Классов" },
  { key: "lessons", label: "Уроков в неделю", short: "Уроков" },
  { key: "windows", label: "Окон у классов", short: "Окон" },
  { key: "violations", label: "Нарушений норм", short: "Нарушений" },
] as const;

function tone(key: (typeof columns)[number]["key"], value: number) {
  if (key === "windows") return "text-ok";
  if (key === "violations") return value === 0 ? "text-ok" : "text-worse";
  return "text-ink";
}

export function Shkoly() {
  return (
    <section className="border-y border-rule bg-sheet py-14 md:py-28">
      <div className="mx-auto max-w-[1400px] px-4 md:px-8">
        <h2 className="max-w-[20ch] text-3xl font-semibold leading-tight tracking-[-0.02em] text-ink md:text-4xl">
          Четыре школы разного размера
        </h2>

        {/* Телефон: карточка на школу. Пять колонок в 375px нечитаемы, а
            горизонтальный скролл тут ворует вертикальный свайп. */}
        <div className="mt-7 grid gap-3 sm:grid-cols-2 md:hidden">
          {schools.map((s) => (
            <div key={s.name} className="rounded-lg border border-rule p-4 sm:p-5">
              <div className="text-[15px] font-semibold text-ink">{s.name}</div>
              <dl className="mt-2.5 grid grid-cols-4 gap-x-3 gap-y-2 sm:grid-cols-2 sm:gap-y-3">
                {columns.map((c) => (
                  <div key={c.key}>
                    <dt className="truncate text-[11px] leading-4 text-pencil sm:text-[12px]">
                      {c.short}
                    </dt>
                    <dd className={`text-[19px] font-semibold sm:text-[20px] ${tone(c.key, s[c.key])}`}>
                      {s[c.key]}
                    </dd>
                  </div>
                ))}
              </dl>
            </div>
          ))}
        </div>

        {/* Планшет и шире: обычная таблица, здесь она читается лучше карточек. */}
        <div className="mt-10 hidden md:block">
          <table className="w-full border-collapse text-left">
            <thead>
              <tr className="border-b border-rule">
                <th className="py-3 pr-4 text-[13px] font-medium text-pencil">Школа</th>
                {columns.map((c) => (
                  <th key={c.key} className="py-3 pr-4 text-[13px] font-medium text-pencil">
                    {c.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {schools.map((s) => (
                <tr key={s.name} className="border-b border-rule last:border-b-0">
                  <td className="py-4 pr-4 text-[15px] font-medium text-ink">{s.name}</td>
                  {columns.map((c) => (
                    <td
                      key={c.key}
                      className={`py-4 pr-4 text-[22px] font-semibold ${tone(c.key, s[c.key])}`}
                    >
                      {s[c.key]}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="mt-7 grid gap-5 md:grid-cols-2 md:gap-16 lg:max-w-[80%]">
          <p className="text-[15px] leading-relaxed text-pencil">
            Ни в одной сетке нет конфликтов и нет окон у классов. Двадцать пять
            нарушений у школы агрогородка — это одна и та же норма, которую в
            этой школе выполнить физически нельзя. Система об этом говорит прямо,
            а не прячет.
          </p>
          <p className="text-[15px] leading-relaxed text-pencil">
            Это модели белорусских школ, построенные по открытым данным, а не
            выгрузки из работающих школ. Размеры, предметы и нормы настоящие;
            проверку на живой тарификации мы сейчас и организуем.
          </p>
        </div>
      </div>
    </section>
  );
}
