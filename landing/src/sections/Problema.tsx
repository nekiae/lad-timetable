export function Problema() {
  return (
    <section className="border-t border-rule bg-sheet py-20 md:py-28">
      <div className="mx-auto max-w-[1400px] px-4 md:px-8">
        <p className="max-w-[20ch] text-3xl font-semibold leading-[1.15] tracking-[-0.02em] text-ink md:text-[44px] md:leading-[1.1]">
          В сентябре расписание ещё переставляют.
        </p>
        <div className="mt-10 grid gap-8 md:grid-cols-2 md:gap-16 lg:max-w-[70%]">
          <p className="text-[17px] leading-relaxed text-pencil">
            Завуч держит в голове всё сразу: часы учебного плана, санитарные
            нормы, свободные кабинеты, методические дни, совместителей и
            пожелания шестидесяти человек. Меняешь один урок — рассыпаются три
            других.
          </p>
          <p className="text-[17px] leading-relaxed text-pencil">
            На это уходят последние недели августа и первые недели сентября. И
            всё равно получается не идеально: кто-то приезжает в школу ради
            одного урока, у кого-то окно посреди дня.
          </p>
        </div>
      </div>
    </section>
  );
}
