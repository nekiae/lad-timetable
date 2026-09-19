import type { Metadata } from "next";
import "@fontsource-variable/ibm-plex-sans";
import "./globals.css";

export const metadata: Metadata = {
  title: "ЛАД — расписание школы",
  description:
    "Система составляет школьное расписание с учётом санитарных норм Беларуси " +
    "и объясняет каждое «нельзя». Первая законная сетка — за секунды.",
  openGraph: {
    title: "ЛАД — Логистика Академического Дня",
    description:
      "Расписание школы, собранное за секунды, с соблюдением санитарных норм Беларуси.",
    locale: "ru_BY",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ru">
      <body>{children}</body>
    </html>
  );
}
