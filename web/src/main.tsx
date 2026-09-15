import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";

// Plex Sans с осями веса и ширины: узкое начертание для сетки — та же семья.
import "@fontsource-variable/ibm-plex-sans/wdth.css";
import "./index.css";
import { Shell } from "./Shell";
import { SchoolsPage } from "./pages/SchoolsPage";
import { SchoolPage } from "./pages/SchoolPage";
import { SchedulePage } from "./pages/SchedulePage";
import { DataPage } from "./pages/data/DataPage";
import { SubstitutionsPage } from "./pages/SubstitutionsPage";
import { PrintPage } from "./pages/PrintPage";
import { WhatIfPage } from "./pages/WhatIfPage";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<SchoolsPage />} />
        <Route path="/s/:id/print" element={<PrintPage />} />
        <Route path="/s/:id" element={<Shell />}>
          <Route path="data" element={<DataPage />} />
          <Route index element={<SchoolPage />} />
          <Route path="schedule" element={<SchedulePage />} />
          <Route path="whatif" element={<WhatIfPage />} />
          <Route path="substitutions" element={<SubstitutionsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </React.StrictMode>,
);
