import { createBrowserRouter, Navigate, type RouteObject } from "react-router-dom";
import { AppShell } from "./layout/AppShell";
import { LiveSessionPage } from "./routes/LiveSessionPage";
import { SkillsPage } from "./routes/SkillsPage";
import { NotebooksPage } from "./routes/NotebooksPage";
import { FilesPage } from "./routes/FilesPage";
import { RunsPage } from "./routes/RunsPage";
import { SettingsPage } from "./routes/SettingsPage";
import { NotFound } from "./routes/NotFound";

export const routes: RouteObject[] = [
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <Navigate to="/heor" replace /> },
      // Keep legacy /live links readable, but render the same AI4HEOR
      // workspace. New navigation always uses /heor.
      { path: "live", element: <LiveSessionPage /> },
      { path: "live/:sessionId", element: <LiveSessionPage /> },
      { path: "heor", element: <LiveSessionPage /> },
      { path: "heor/:sessionId", element: <LiveSessionPage /> },
      { path: "skills", element: <SkillsPage /> },
      { path: "notebooks", element: <NotebooksPage /> },
      { path: "files", element: <FilesPage /> },
      { path: "runs", element: <RunsPage /> },
      { path: "settings", element: <SettingsPage /> },
      { path: "*", element: <NotFound /> },
    ],
  },
];

export const router = createBrowserRouter(routes);
