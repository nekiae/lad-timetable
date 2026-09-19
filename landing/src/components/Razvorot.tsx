/** Числовой разворот: одна мысль цифрами на всю ширину. Стоит между
 *  текстовыми секциями и даёт странице ритм. Больше двух на страницу
 *  не ставим, иначе приём перестаёт работать. */
export function Razvorot({
  items,
  note,
}: {
  items: { value: string; label: string; tone?: "ink" | "ok" }[];
  note?: string;
}) {
  return (
    <section className="border-y border-rule bg-sheet py-16 md:py-20">
      <div className="mx-auto max-w-[1400px] px-4 md:px-8">
        <div className="grid gap-8 sm:grid-cols-3 sm:gap-6">
          {items.map((it) => (
            <div key={it.label}>
              <div
                className={`text-[52px] font-semibold leading-[0.95] tracking-[-0.03em] tabular-nums md:text-[68px] ${
                  it.tone === "ok" ? "text-ok" : "text-ink"
                }`}
              >
                {it.value}
              </div>
              <div className="mt-2 text-[15px] leading-snug text-pencil">
                {it.label}
              </div>
            </div>
          ))}
        </div>
        {note && (
          <p className="mt-10 max-w-[64ch] text-[15px] leading-relaxed text-pencil">
            {note}
          </p>
        )}
      </div>
    </section>
  );
}
