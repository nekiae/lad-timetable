import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// В разработке фронт живёт на :5173, API — на :8000 (uvicorn).
// В проде оба отдаёт один FastAPI, поэтому пути /api одинаковы.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
});
