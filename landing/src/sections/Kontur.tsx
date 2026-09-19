export function Kontur() {
  return (
    <section className="border-y border-rule bg-sheet py-20 md:py-28">
      <div className="mx-auto max-w-[1400px] px-4 md:px-8">
        <div className="grid gap-10 md:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)] md:gap-20">
          <h2 className="text-3xl font-semibold leading-tight tracking-[-0.02em] text-ink md:text-4xl">
            Ставится внутри вашего контура
          </h2>
          <div className="space-y-6">
            <Point title="Данные учеников не нужны вообще">
              Системе нужны классы, кабинеты, учителя и тарификация. Фамилий,
              оценок и личных дел учащихся она не запрашивает ни в каком виде и
              хранить их не может.
            </Point>
            <Point title="Работает на ваших серверах">
              Не облачный сервис на чужой стороне. Разворачивается внутри
              школьной или ведомственной инфраструктуры, без выхода данных
              наружу.
            </Point>
            <Point title="Может быть модулем, а не отдельной программой">
              Солвер живёт за обычным HTTP-интерфейсом. Существующая система
              отдаёт тарификацию и получает готовую сетку, завуч продолжает
              работать в привычном окне.
            </Point>
          </div>
        </div>
      </div>
    </section>
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
