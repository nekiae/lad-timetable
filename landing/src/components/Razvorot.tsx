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
    <section className="border-y border-rule bg-sheet py-12 md:py-20">
      <div className="mx-auto max-w-[1400px] px-4 md:px-8">
        <div className="grid grid-cols-3 gap-4 sm:gap-6">
          {items.map((it) => (
            <div key={it.label}>
              <div
                className={`text-[34px] font-semibold leading-[0.95] tracking-[-0.03em] tabular-nums sm:text-[52px] md:text-[68px] ${
                  it.tone === "ok" ? "text-ok" : "text-ink"
                }`}
              >
                {it.value}
              </div>
              <div className="mt-1.5 text-[13px] leading-snug text-pencil sm:mt-2 sm:text-[15px]">
                {it.label}
              </div>
            </div>
          ))}
        </div>
        {note && (
          <p className="mt-7 max-w-[64ch] text-[15px] leading-relaxed text-pencil">
            {note}
          </p>
        )}
      </div>
    </section>
  );
}
