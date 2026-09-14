import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";

import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/500.css";
import "@fontsource/ibm-plex-sans/600.css";
import "@fontsource/ibm-plex-sans/700.css";
import "@fontsource/ibm-plex-sans-condensed/400.css";
import "@fontsource/ibm-plex-sans-condensed/500.css";
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
