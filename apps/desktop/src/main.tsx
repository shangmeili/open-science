import "./lib/polyfills";
import React from "react";
import ReactDOM from "react-dom/client";
import { RouterProvider } from "react-router-dom";
import "./i18n";
import { LocaleProvider } from "./app/providers/LocaleProvider";
import { ThemeProvider } from "./app/providers/ThemeProvider";
import { router } from "./app/router";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <LocaleProvider>
      <ThemeProvider>
        <RouterProvider router={router} />
      </ThemeProvider>
    </LocaleProvider>
  </React.StrictMode>,
);
