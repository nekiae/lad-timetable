import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useParams } from "react-router-dom";

import { api } from "./api";
import { cx } from "./ui";

// Шапка школы сверху, а не боковое меню: сетка на 24 класса шире любого
// экрана, и каждый пиксель ширины отдан ей (docs/DESIGN.md §6).
// Разделы идут в порядке работы завуча.
export function Shell() {
  const { id = "" } = useParams();
  const [name, setName] = useState("");

  useEffect(() => {
    api.school(id).then((s) => setName(String(s.doc.settings.name || "Школа без названия")));
  }, [id]);

  const tab = ({ isActive }: { isActive: boolean }) =>
    cx("flex h-14 items-center border-b-2 px-1 font-medium transition-colors duration-150",
       isActive ? "border-pen text-pen" : "border-transparent text-pencil hover:text-ink");

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-40 border-b border-rule bg-sheet print:hidden">
        <div className="flex items-center gap-x-8 gap-y-1 px-4 max-sm:flex-wrap md:px-8">
          <div className="flex min-w-0 items-baseline gap-3 max-sm:pt-3">
            <Link to="/" className="text-heading font-bold tracking-tight">ЛАД</Link>
            <span className="truncate text-small text-pencil">{name}</span>
          </div>
          <nav className="flex gap-6 overflow-x-auto">
            <NavLink to={`/s/${id}/data`} className={tab}>Данные</NavLink>
            <NavLink to={`/s/${id}`} end className={tab}>Составление</NavLink>
            <NavLink to={`/s/${id}/schedule`} className={tab}>Расписание</NavLink>
            <NavLink to={`/s/${id}/whatif`} className={tab}>Что если</NavLink>
            <NavLink to={`/s/${id}/substitutions`} className={tab}>Замены</NavLink>
          </nav>
        </div>
      </header>
      <main className="min-w-0 flex-1">
        <Outlet />
      </main>
    </div>
  );
}
