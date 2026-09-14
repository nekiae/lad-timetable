import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api } from "../api";
import { Button } from "../ui";

// Первый экран. Человек пришёл, чтобы получить расписание своей школы,
// поэтому здесь два действия: открыть свою или посмотреть на примере.
export function SchoolsPage() {
  const [schools, setSchools] = useState<{ id: string; name: string; updated_at: number }[]>();
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    api.schools().then(setSchools);
  }, []);

  async function create(fromExample: boolean) {
    setBusy(true);
    const { id } = await api.createSchool("", fromExample);
    navigate(fromExample ? `/s/${id}` : `/s/${id}/data`);
  }

  return (
    <div className="min-h-screen px-4 py-16 md:px-8 md:py-24">
      <div className="mx-auto max-w-3xl">
        <h1 className="text-[44px] font-semibold leading-[48px] tracking-tight">ЛАД</h1>
        <p className="mt-4 max-w-prose text-heading font-normal text-ink/85">
          Расписание школы по санитарным нормам Республики Беларусь. Вносите нагрузку —
          система составляет сетку без окон у классов и объясняет каждое своё решение.
        </p>

        <div className="mt-8 flex flex-wrap gap-3">
          <Button variant="primary" size="lg" disabled={busy} onClick={() => create(false)}>
            Внести свою школу
          </Button>
          <Button size="lg" disabled={busy} onClick={() => create(true)}>
            Открыть пример на 24 класса
          </Button>
        </div>

        {schools && schools.length > 0 && (
          <section className="mt-16">
            <h2 className="mb-3 text-heading">Ваши школы</h2>
            <ul className="divide-y divide-rule rounded-lg border border-rule bg-sheet">
              {schools.map((s) => (
                <li key={s.id}>
                  <Link to={`/s/${s.id}`}
                        className="flex flex-wrap items-baseline justify-between gap-x-4 px-4 py-3 transition-colors duration-150 hover:bg-paper">
                    <span className="font-medium">{s.name}</span>
                    <span className="text-small text-pencil">
                      изменено {new Date(s.updated_at * 1000).toLocaleString("ru-RU", {
                        day: "numeric", month: "long", hour: "2-digit", minute: "2-digit",
                      })}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </div>
  );
}
