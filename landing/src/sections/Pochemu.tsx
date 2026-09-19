/** Причины разложены как замечания на полях тетради: пометка красной ручкой
 *  слева, запись справа. Поле у страницы уже нарисовано (.pole), и до сих
 *  пор оно пустовало. */
const reasons = [
  {
    mark: "",
    title: "Дело не в алгоритме",
    body:
      "Составление расписания изучают шестьдесят лет, готовые солверы есть у всех. " +
      "Untis, aSc, «Ректор» работают и продаются. Но завуч всё равно сидит с бумагой.",
  },
  {
    mark: "вот тут и стоит вся страна",
    title: "Восемьдесят процентов работы — это ввод данных",
    body:
      "Чтобы солвер заработал, надо формализовать нагрузку, деления на подгруппы, " +
      "совместительство, кабинетный фонд. Эту часть не автоматизировал никто.",
  },
  {
    mark: "",
    title: "Половина ограничений нигде не записана",
    body:
      "«Иванова по вторникам не может», «химию нельзя после физры». Это живёт в " +
      "голове завуча, а не в таблице, и ни одна импортная система об этом не спросит.",
  },
  {
    mark: "",
    title: "Санитарные нормы здесь свои",
    body:
      "Импортные системы знают чужие нормы, «Ректор» настраивается под российский " +
      "СанПиН руками. Беларусь живёт по ССЭТ № 525, и его надо знать из коробки.",
  },
];

export function Pochemu() {
  return (
    <section className="tetrad pole">
      <div className="mx-auto max-w-[1400px] px-4 py-14 md:px-8 md:py-28">
        <h2 className="max-w-[16ch] text-3xl font-semibold leading-tight tracking-[-0.02em] text-ink md:text-4xl">
          Почему это до сих пор делают руками
        </h2>
        <dl className="mt-8 space-y-7 md:mt-14 md:space-y-12">
          {reasons.map((r) => (
            <div key={r.title} className="border-l-2 border-no/25 pl-4 md:pl-5">
              <dt className="text-[18px] font-semibold leading-6 text-ink md:text-[21px] md:leading-7">
                {r.title}
              </dt>
              <dd className="mt-1.5 max-w-[60ch] text-[15px] leading-relaxed text-pencil md:text-[16px]">
                {r.body}
              </dd>
              {r.mark && (
                <div
                  aria-hidden="true"
                  className="mt-2 text-[14px] font-medium text-no"
                  style={{ transform: "rotate(-1.4deg)" }}
                >
                  {r.mark}
                </div>
              )}
            </div>
          ))}
        </dl>
      </div>
    </section>
  );
}
