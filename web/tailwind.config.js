/** @type {import('tailwindcss').Config} */
// Токены ЛАД. Смысл каждого — в docs/DESIGN.md §3–5; новый токен сначала
// описывается там. Палитра — школьная тетрадь: бумага, синие чернила,
// карандаш, красная ручка. Имена ok / worse / no совпадают с Verdict.level.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        paper: "#F6F8FB",
        sheet: "#FFFFFF",
        rule: "#DDE4EF",
        ink: "#1C2B4F",
        pencil: "#5F6A84",
        pen: { DEFAULT: "#2346B0", strong: "#1B3990", soft: "#E6ECFA" },
        ok: { DEFAULT: "#2F7D55", soft: "#E5F3EB" },
        worse: { DEFAULT: "#9A6200", soft: "#FBF1DC" },
        no: { DEFAULT: "#C9302C", soft: "#FBEAE9" },
      },
      fontFamily: {
        sans: ['"IBM Plex Sans"', "system-ui", "-apple-system", '"Segoe UI"', "sans-serif"],
        narrow: ['"IBM Plex Sans Condensed"', '"IBM Plex Sans"', '"Arial Narrow"', "sans-serif"],
      },
      fontSize: {
        title: ["28px", { lineHeight: "34px", fontWeight: "600", letterSpacing: "-0.01em" }],
        heading: ["17px", { lineHeight: "24px", fontWeight: "600" }],
        body: ["15px", { lineHeight: "22px" }],
        small: ["13px", { lineHeight: "18px" }],
        cell: ["13px", { lineHeight: "16px" }],
        metric: ["22px", { lineHeight: "26px", fontWeight: "600" }],
      },
      borderRadius: {
        DEFAULT: "6px",
        lg: "10px",
      },
      boxShadow: {
        pop: "0 8px 24px rgb(28 43 79 / 0.14)",
      },
    },
  },
  plugins: [],
};
