/** @type {import('tailwindcss').Config} */
// Палитра — из школьной тетради: бумага в клетку, синие чернила, красная ручка
// учителя. Красный зарезервирован за нарушениями и больше нигде не появляется.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        paper: "#F6F8FB",
        rule: "#DDE4EF",
        ink: "#1C2B4F",
        pen: { DEFAULT: "#2346B0", soft: "#E6ECFA" },
        red: { pen: "#C9302C", soft: "#FBEAE9" },
        pencil: "#8792A8",
        ok: { DEFAULT: "#2F7D55", soft: "#E5F3EB" },
        warn: { DEFAULT: "#A86A00", soft: "#FBF1DC" },
      },
      fontFamily: {
        sans: ["Onest", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
      },
    },
  },
  plugins: [],
};
