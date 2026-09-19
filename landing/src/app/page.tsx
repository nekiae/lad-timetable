import { Header } from "@/components/Header";
import { Footer } from "@/components/Footer";
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
        <Sborka />
        <Shkoly />
        <Obyasnimost />
        <Zameny />
        <Kontur />
        <Kontakt />
      </main>
      <Footer />
    </div>
  );
}
