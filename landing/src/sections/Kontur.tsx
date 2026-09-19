export function Kontur() {
  return (
    <section className="border-y border-rule bg-sheet py-14 md:py-28">
      <div className="mx-auto max-w-[1400px] px-4 md:px-8">
        <h2 className="max-w-[18ch] text-3xl font-semibold leading-tight tracking-[-0.02em] text-ink md:text-4xl">
          Ставится внутри вашего контура
        </h2>

        {/* Схема потока данных. Единственная графика на странице, и она
            несёт содержание: видно, что за пунктирную рамку ничего
            не выходит. */}
        <div className="mt-7 rounded-lg border border-dashed border-pen/45 p-4 sm:p-6 md:mt-12 md:p-8">
          <div className="text-[13px] font-medium text-pen">
            Контур школы или ведомства
          </div>

          <div className="mt-4 grid items-stretch gap-2 md:gap-4 md:grid-cols-[minmax(0,1fr)_28px_minmax(0,1.1fr)_28px_minmax(0,1fr)]">
            <Blok title="Тарификация" body="Классы, кабинеты, учителя, часы" />
            <Strelka />
            <Blok
              title="ЛАД"
              body="Солвер, санитарные нормы, объяснения"
              glavny
            />
            <Strelka />
            <Blok title="Готовая сетка" body="Расписание, замены, выгрузка" />
          </div>

          <p className="mt-5 text-[15px] leading-relaxed text-pencil">
            Наружу не уходит ничего. Данные учеников системе не нужны ни в каком
            виде: фамилий, оценок и личных дел она не запрашивает и хранить их
            не может.
          </p>
        </div>

        <div className="mt-8 grid gap-6 md:grid-cols-2 md:gap-16">
          <Point title="Работает на ваших серверах">
            Не облачный сервис на чужой стороне. Разворачивается внутри школьной
            или ведомственной инфраструктуры.
          </Point>
          <Point title="Может быть модулем, а не отдельной программой">
            Солвер живёт за обычным HTTP-интерфейсом. Существующая система
            отдаёт тарификацию и получает готовую сетку, завуч продолжает
            работать в привычном окне.
          </Point>
        </div>
      </div>
    </section>
  );
}

function Blok({
  title,
  body,
  glavny = false,
}: {
  title: string;
  body: string;
  glavny?: boolean;
}) {
  return (
    <div
      className={`rounded border p-4 ${
        glavny ? "border-pen bg-pen-soft" : "border-rule bg-paper"
      }`}
    >
      <div
        className={`text-[15px] font-semibold ${
          glavny ? "text-pen" : "text-ink"
        }`}
      >
        {title}
      </div>
      <div className="mt-1 text-[13px] leading-5 text-pencil">{body}</div>
    </div>
  );
}

/** На узком экране стрелка смотрит вниз, на широком вправо. */
function Strelka() {
  return (
    <div
      aria-hidden="true"
      className="flex items-center justify-center text-[18px] leading-none text-pencil"
    >
      <span className="md:hidden">↓</span>
      <span className="hidden md:inline">→</span>
    </div>
  );
}

function Point({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="border-t border-rule pt-4">
      <h3 className="text-[17px] font-semibold text-ink">{title}</h3>
      <p className="mt-2 max-w-[60ch] text-[15px] leading-relaxed text-pencil">
        {children}
      </p>
    </div>
  );
}
