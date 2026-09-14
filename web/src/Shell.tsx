import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useParams } from "react-router-dom";

import { api } from "./api";

// Оболочка школы: слева — где я и куда можно пойти, справа — работа.
// Разделов немного, и они идут в порядке работы завуча, поэтому это
// простой список, а не меню с иконками.
export function Shell() {
  const { id = "" } = useParams();
  const [name, setName] = useState("");

  useEffect(() => {
    api.school(id).then((s) => setName(String(s.doc.settings.name || "Школа без названия")));
  }, [id]);

  const item = ({ isActive }: { isActive: boolean }) =>
    `block rounded-md px-3 py-2 ${isActive ? "bg-pen-soft font-medium text-pen" : "text-ink hover:bg-white"}`;

  return (
    <div className="flex min-h-screen">
      <aside className="flex w-60 shrink-0 flex-col border-r border-rule bg-paper px-4 py-5 max-md:hidden">
        <Link to="/" className="mb-6 text-2xl font-bold tracking-tight text-ink">
          ЛАД
        </Link>
        <p className="mb-4 text-sm leading-snug text-pencil">{name}</p>
        <nav className="space-y-1">
          <NavLink to={`/s/${id}`} end className={item}>
            Школа и составление
          </NavLink>
          <NavLink to={`/s/${id}/schedule`} className={item}>
            Расписание
          </NavLink>
        </nav>
      </aside>
      <main className="min-w-0 flex-1">
        <Outlet />
      </main>
    </div>
  );
}
