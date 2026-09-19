import { Header } from "@/components/Header";
import { Footer } from "@/components/Footer";
import { Razvorot } from "@/components/Razvorot";
import { Hero } from "@/sections/Hero";
import { Problema } from "@/sections/Problema";
import { Pochemu } from "@/sections/Pochemu";
import { Sborka } from "@/sections/Sborka";
import { Shkoly } from "@/sections/Shkoly";
import { Obyasnimost } from "@/sections/Obyasnimost";
import { Zameny } from "@/sections/Zameny";
import { Kontur } from "@/sections/Kontur";
import { Kontakt } from "@/sections/Kontakt";

export default function Page() {
  return (
    <div id="top">
      <Header />
      <main>
        <Hero />
        <Problema />
        <Pochemu />
        {/* Цифры школы завуча: out/demo/demo_zhemchuzhny_report.json,
            время первой сетки — STATUS.md. */}
        <Razvorot
          items={[
            { value: "838", label: "уроков в неделю на школе в 24 класса" },
            { value: "0", label: "конфликтов в сетке", tone: "ok" },
            { value: "2,4 с", label: "до первой готовой сетки" },
          ]}
        />
        <Sborka />
        <Shkoly />
        <Obyasnimost />
        <Zameny />
        {/* 1414 городских школ — docs/POSITIONING.md; отсутствие единой
            системы автосоставления — CLAUDE.md §4.1. */}
        <Razvorot
          items={[
            { value: "1414", label: "городских школ в Беларуси" },
            { value: "2817", label: "школ всего по стране" },
            { value: "0", label: "единых систем автосоставления" },
          ]}
          note="Расписание в них составляют руками. Отдельные школы покупают программы сами, по решению завуча или директора, без всякой централизации."
        />
        <Kontur />
        <Kontakt />
      </main>
      <Footer />
    </div>
  );
}
