/** Цифры из out/demo/*_report.json, посчитаны валидатором проекта.
 *  Все четыре школы - модели по открытым данным, а не выгрузки из
 *  работающих школ. Так и написано под таблицей. */
const schools = [
  { name: "Сельская школа", classes: 7, lessons: 236, windows: 0, violations: 0 },
  { name: "Школа райцентра", classes: 14, lessons: 490, windows: 0, violations: 0 },
  { name: "Школа агрогородка", classes: 24, lessons: 838, windows: 0, violations: 25 },
  { name: "Городская гимназия", classes: 28, lessons: 980, windows: 0, violations: 3 },
];

export function Shkoly() {
  return (
    <section className="border-y border-rule bg-sheet py-20 md:py-28">
      <div className="mx-auto max-w-[1400px] px-4 md:px-8">
        <h2 className="max-w-[20ch] text-3xl font-semibold leading-tight tracking-[-0.02em] text-ink md:text-4xl">
          Четыре школы разного размера
        </h2>

        <div className="mt-10 overflow-x-auto">
          <table className="w-full min-w-[640px] border-collapse text-left">
            <thead>
              <tr className="border-b border-rule">
                <th className="py-3 pr-4 text-[13px] font-medium text-pencil">Школа</th>
                <th className="py-3 pr-4 text-[13px] font-medium text-pencil">Классов</th>
                <th className="py-3 pr-4 text-[13px] font-medium text-pencil">Уроков в неделю</th>
                <th className="py-3 pr-4 text-[13px] font-medium text-pencil">Окон у классов</th>
                <th className="py-3 text-[13px] font-medium text-pencil">Нарушений норм</th>
              </tr>
            </thead>
            <tbody>
              {schools.map((s) => (
                <tr key={s.name} className="border-b border-rule last:border-b-0">
                  <td className="py-4 pr-4 text-[15px] font-medium text-ink">{s.name}</td>
                  <td className="py-4 pr-4 text-[22px] font-semibold text-ink">{s.classes}</td>
                  <td className="py-4 pr-4 text-[22px] font-semibold text-ink">{s.lessons}</td>
                  <td className="py-4 pr-4 text-[22px] font-semibold text-ok">{s.windows}</td>
                  <td
                    className={`py-4 text-[22px] font-semibold ${
                      s.violations === 0 ? "text-ok" : "text-worse"
                    }`}
                  >
                    {s.violations}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="mt-8 grid gap-6 md:grid-cols-2 md:gap-16 lg:max-w-[80%]">
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
