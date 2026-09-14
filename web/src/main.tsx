import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";

import "./index.css";
import { Shell } from "./Shell";
import { SchoolsPage } from "./pages/SchoolsPage";
import { SchoolPage } from "./pages/SchoolPage";
import { SchedulePage } from "./pages/SchedulePage";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<SchoolsPage />} />
        <Route path="/s/:id" element={<Shell />}>
          <Route index element={<SchoolPage />} />
          <Route path="schedule" element={<SchedulePage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </React.StrictMode>,
);
