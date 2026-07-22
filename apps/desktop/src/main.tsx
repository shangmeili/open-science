import "./lib/polyfills";
import React from "react";
import ReactDOM from "react-dom/client";
import { RouterProvider } from "react-router-dom";
import "./i18n";
import { LocaleProvider } from "./app/providers/LocaleProvider";
import { ThemeProvider } from "./app/providers/ThemeProvider";
import { ZoomProvider } from "./app/providers/ZoomProvider";
import { router } from "./app/router";
import { installGatewayAuthGuard } from "./lib/webMode";
import "./index.css";

// Web client: catch gateway 401s (rotated/revoked token) → re-auth. Installed
// before any OpenCodeClient binds fetch.
installGatewayAuthGuard();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <LocaleProvider>
      <ThemeProvider>
        <ZoomProvider>
          <RouterProvider router={router} />
        </ZoomProvider>
      </ThemeProvider>
    </LocaleProvider>
  </React.StrictMode>,
);
