const reasons = [
  {
    title: "Дело не в алгоритме",
    body:
      "Составление расписания изучают шестьдесят лет, готовые солверы есть у всех. " +
      "Untis, aSc, «Ректор» работают и продаются. Но завуч всё равно сидит с бумагой.",
  },
  {
    title: "Восемьдесят процентов работы — это ввод данных",
    body:
      "Чтобы солвер заработал, надо формализовать нагрузку, деления на подгруппы, " +
      "совместительство, кабинетный фонд. Эту часть не автоматизировал никто.",
  },
  {
    title: "Половина ограничений нигде не записана",
    body:
      "«Иванова по вторникам не может», «химию нельзя после физры». Это живёт в " +
      "голове завуча, а не в таблице, и ни одна импортная система об этом не спросит.",
  },
  {
    title: "Санитарные нормы здесь свои",
    body:
      "Импортные системы знают чужие нормы, «Ректор» настраивается под российский " +
      "СанПиН руками. Беларусь живёт по ССЭТ № 525, и его надо знать из коробки.",
  },
];

export function Pochemu() {
  return (
    <section className="mx-auto max-w-[1400px] px-4 py-20 md:px-8 md:py-28">
      <h2 className="max-w-[16ch] text-3xl font-semibold leading-tight tracking-[-0.02em] text-ink md:text-4xl">
        Почему это до сих пор делают руками
      </h2>
      <dl className="mt-12 grid gap-x-16 gap-y-10 md:grid-cols-2">
        {reasons.map((r) => (
          <div key={r.title}>
            <dt className="text-[17px] font-semibold leading-6 text-ink">
              {r.title}
            </dt>
            <dd className="mt-2 max-w-[52ch] text-[15px] leading-relaxed text-pencil">
              {r.body}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
