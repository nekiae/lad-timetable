import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api } from "../api";

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
    navigate(`/s/${id}`);
  }

  return (
    <div className="notebook min-h-screen px-4 py-16">
      <div className="mx-auto max-w-2xl">
        <h1 className="text-5xl font-bold tracking-tight">ЛАД</h1>
        <p className="mt-4 max-w-xl text-lg text-ink/80">
          Расписание школы по санитарным нормам Республики Беларусь. Вносите нагрузку —
          система составляет сетку без окон у классов и объясняет каждое своё решение.
        </p>

        <div className="mt-8 flex flex-wrap gap-3">
          <button className="btn-primary" disabled={busy} onClick={() => create(false)}>
            Внести свою школу
          </button>
          <button className="btn-quiet" disabled={busy} onClick={() => create(true)}>
            Открыть пример на 24 класса
          </button>
        </div>

        {schools && schools.length > 0 && (
          <section className="mt-14">
            <h2 className="mb-3 text-sm font-medium text-pencil">Ваши школы</h2>
            <ul className="divide-y divide-rule rounded-lg border border-rule bg-white">
              {schools.map((s) => (
                <li key={s.id}>
                  <Link to={`/s/${s.id}`} className="flex items-baseline justify-between px-4 py-3 hover:bg-paper">
                    <span className="font-medium">{s.name}</span>
                    <span className="text-sm text-pencil">
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
