export function Header() {
  return (
    <header className="sticky top-0 z-50 border-b border-rule bg-paper/95 backdrop-blur-sm">
      <div className="mx-auto flex h-16 max-w-[1400px] items-center justify-between gap-6 px-4 md:px-8">
        <a href="#top" className="flex items-baseline gap-2.5">
          <span className="text-[19px] font-semibold tracking-[-0.01em] text-ink">
            ЛАД
          </span>
          <span className="hidden text-[13px] text-pencil sm:inline">
            Логистика Академического Дня
          </span>
        </a>
        <nav className="flex items-center gap-5">
          <a
            href="#sborka"
            className="hidden text-[15px] text-pencil transition-colors duration-150 hover:text-ink md:inline"
          >
            Как работает
          </a>
          <a
            href="https://t.me/nekivlad"
            className="rounded bg-pen px-4 py-2 text-[15px] font-semibold text-white transition-transform duration-150 hover:bg-pen-strong active:translate-y-px"
          >
            Написать
          </a>
        </nav>
      </div>
    </header>
  );
}
