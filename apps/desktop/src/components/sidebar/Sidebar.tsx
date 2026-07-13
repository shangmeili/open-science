import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import {
  ChevronRight,
  Activity,
  Files,
  FlaskConical,
  Folder,
  FolderOpen,
  FolderTree,
  NotebookPen,
  PanelLeft,
  Plus,
  Settings,
  Trash2,
} from "lucide-react";
import type { Project } from "@ai4s/shared";
import { cn } from "@/lib/cn";
import { useRuntimeStore } from "@/lib/runtime";
import { renameProject, type ProjectInfo } from "@/lib/tauri";
import {
  SIDEBAR_MAX,
  SIDEBAR_MIN,
  useOverlayTitlebar,
  useUiStore,
} from "@/lib/store";
import { useUpdateStore } from "@/lib/update";
import { StatusPills } from "./StatusPills";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import logo from "@/assets/logo.webp";

interface Row {
  id: string;
  title: string;
  to: string;
  kind: "session" | "example";
}

/** Dragging the divider below this pointer x collapses the sidebar; dragging
 *  back past it re-expands. Sits below SIDEBAR_MIN so there is a clear "snap". */
const COLLAPSE_BELOW = 140;

/** Projects the user folded shut (ids). Projects default to open — a
 *  researcher has a handful, and their sessions ARE the sidebar's content. */
const COLLAPSED_KEY = "ai4s.collapsedProjects";
function initialCollapsedProjects(): string[] {
  if (typeof window === "undefined") return [];
  try {
    return JSON.parse(window.localStorage.getItem(COLLAPSED_KEY) ?? "[]");
  } catch {
    return [];
  }
}

export function Sidebar({ project }: { project: Project }) {
  const { t } = useTranslation("nav");
  const navigate = useNavigate();
  const location = useLocation();
  const {
    sessions,
    projects,
    workspace,
    hiddenExamples,
    startDraft,
    startDraftInWorkspace,
    createProject,
    refreshProjects,
    deleteSession,
    hideExample,
  } = useRuntimeStore();
  const showUpdateBadge = useUpdateStore((s) => s.showBadge);
  const {
    sidebarCollapsed,
    sidebarWidth,
    setSidebarCollapsed,
    setSidebarWidth,
    toggleSidebar,
  } = useUiStore();
  // While dragging, the live width lives here; the store (and localStorage)
  // are only written on pointer-up.
  const [dragWidth, setDragWidth] = useState<number | null>(null);
  const dragging = dragWidth !== null;

  const onDividerPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.currentTarget.setPointerCapture(e.pointerId);
    setDragWidth(sidebarWidth);
  };

  const onDividerPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!dragging) return;
    // The sidebar starts at the window's left edge, so clientX is the width.
    const x = e.clientX;
    if (x < COLLAPSE_BELOW) {
      if (!sidebarCollapsed) setSidebarCollapsed(true);
      return;
    }
    if (sidebarCollapsed) setSidebarCollapsed(false);
    setDragWidth(Math.min(SIDEBAR_MAX, Math.max(SIDEBAR_MIN, x)));
  };

  const onDividerPointerUp = () => {
    if (!dragging) return;
    setSidebarWidth(dragWidth);
    setDragWidth(null);
  };

  const startNew = () => {
    startDraft();
    navigate("/live");
  };

  // ---- Projects: sessions group under a project by workspace folder ----
  const [collapsedProjects, setCollapsedProjects] = useState<string[]>(
    initialCollapsedProjects,
  );
  const [creatingProject, setCreatingProject] = useState(false);
  const [createBusy, setCreateBusy] = useState(false);
  const [renamingId, setRenamingId] = useState<string | null>(null);

  const toggleProject = (id: string) =>
    setCollapsedProjects((prev) => {
      const next = prev.includes(id)
        ? prev.filter((x) => x !== id)
        : [...prev, id];
      if (typeof window !== "undefined")
        window.localStorage.setItem(COLLAPSED_KEY, JSON.stringify(next));
      return next;
    });

  const submitNewProject = async (name: string) => {
    const trimmed = name.trim();
    if (!trimmed || createBusy) {
      setCreatingProject(false);
      return;
    }
    setCreateBusy(true);
    const created = await createProject(trimmed);
    setCreateBusy(false);
    setCreatingProject(false);
    if (created) navigate("/live");
  };

  const newSessionIn = async (p: ProjectInfo) => {
    await startDraftInWorkspace(p.path);
    navigate("/live");
  };

  const submitRename = async (p: ProjectInfo, name: string) => {
    setRenamingId(null);
    const trimmed = name.trim();
    if (!trimmed || trimmed === p.name) return;
    try {
      await renameProject(p.path, trimmed);
      await refreshProjects();
    } catch {
      /* the sidebar keeps showing the old name */
    }
  };

  // Subagent child sessions are internals of their parent conversation —
  // their asks and progress surface there, so they get no row of their own.
  const topSessions = sessions.filter((s) => !s.parentId);
  const projectByPath = new Map(projects.map((p) => [p.path, p]));
  const sessionsByProject = new Map<string, Row[]>(
    projects.map((p) => [p.id, []]),
  );
  const looseRows: Row[] = [];
  for (const s of topSessions) {
    const row: Row = {
      id: s.id,
      title: s.title,
      to: `/live/${s.id}`,
      kind: "session",
    };
    const owner = s.directory ? projectByPath.get(s.directory) : undefined;
    if (owner) sessionsByProject.get(owner.id)!.push(row);
    else looseRows.push(row);
  }
  const exampleRows: Row[] = project.sessions
    .filter((e) => !hiddenExamples.includes(e.id))
    .map((e) => ({
      id: e.id,
      title: e.title,
      to: `/example/${e.id}`,
      kind: "example" as const,
    }));

  const [pendingDelete, setPendingDelete] = useState<Row | null>(null);

  const confirmDelete = () => {
    const row = pendingDelete;
    setPendingDelete(null);
    if (!row) return;
    if (row.kind === "session") void deleteSession(row.id);
    else hideExample(row.id);
    if (location.pathname === row.to) navigate("/live");
  };

  // With the overlay titlebar (macOS), reserve a draggable strip at the top so
  // the traffic lights don't overlap the logo and the window stays movable.
  const isMac = navigator.userAgent.includes("Mac");
  const overlayTitlebar = useOverlayTitlebar();

  const width = dragWidth ?? sidebarWidth;

  const sessionRow = (row: Row) => (
    <div key={row.to} className="group relative">
      <NavLink
        to={row.to}
        className={cn(
          "flex items-center gap-2 rounded-input py-1 pl-2 pr-8 text-[13px] hover:bg-surface-2",
          location.pathname === row.to
            ? "bg-surface-2 text-text"
            : "text-text/90",
        )}
      >
        <span
          className={cn(
            "h-1.5 w-1.5 shrink-0 rounded-full",
            row.kind === "example" ? "bg-muted" : "bg-ok",
          )}
        />
        <span className="flex-1 truncate">{row.title}</span>
        {row.kind === "example" && (
          <span className="shrink-0 rounded-full bg-surface-2 px-1.5 text-[10px] uppercase tracking-wide text-muted ring-1 ring-border">
            {t("history.exampleTag")}
          </span>
        )}
      </NavLink>
      <button
        onClick={() => setPendingDelete(row)}
        aria-label={t("history.deleteAria", { title: row.title })}
        className="absolute right-1.5 top-1/2 hidden -translate-y-1/2 rounded p-1 text-muted hover:bg-border hover:text-error group-hover:block"
      >
        <Trash2 size={13} />
      </button>
    </div>
  );

  return (
    <div
      className={cn(
        "relative h-full shrink-0 overflow-hidden",
        !dragging && "transition-[width] duration-200 ease-out",
      )}
      style={{ width: sidebarCollapsed ? 0 : width }}
    >
      <aside
        className="flex h-full flex-col border-r border-border bg-surface"
        style={{ width }}
      >
        {/* The strip clears the traffic lights and hosts the collapse button just
          right of them — same spot the expand button lands when collapsed. */}
        {overlayTitlebar && (
          <div
            data-tauri-drag-region
            className="flex h-12 shrink-0 items-center pl-[78px]"
          >
            <button
              onClick={toggleSidebar}
              aria-label={t("sidebar.collapse")}
              title={t("sidebar.collapseTitle", { shortcut: "⌘B" })}
              className="rounded p-1 text-text hover:bg-surface-2"
            >
              <PanelLeft size={14} strokeWidth={1.5} />
            </button>
          </div>
        )}
        <div className={cn("px-4 pb-3", overlayTitlebar ? "pt-1" : "pt-4")}>
          <div className="flex items-baseline gap-1.5">
            <img src={logo} alt="" className="h-[18px] w-auto self-center" />
            {/* eslint-disable-next-line i18next/no-literal-string -- product brand name, not translated across locales */}
            <div className="font-serif text-[17px] font-semibold leading-none tracking-tight text-text">
              AI4HEOR
            </div>
            <span className="text-[10px] uppercase tracking-widest text-muted">
              {t("sidebar.betaBadge")}
            </span>
            {!overlayTitlebar && (
              <button
                onClick={toggleSidebar}
                aria-label={t("sidebar.collapse")}
                title={t("sidebar.collapseTitle", {
                  shortcut: isMac ? "⌘B" : "Ctrl+B",
                })}
                className="ml-auto self-center rounded p-1 text-text hover:bg-surface-2"
              >
                <PanelLeft size={14} strokeWidth={1.5} />
              </button>
            )}
          </div>
        </div>

        <nav className="flex flex-col px-3">
          <NavRow
            icon={<Plus size={16} />}
            label={t("items.new")}
            onClick={startNew}
          />
          <NavRow
            icon={<Activity size={16} />}
            label={t("items.heor")}
            onClick={() => navigate("/heor")}
            active={location.pathname.startsWith("/heor")}
          />
          <NavRow
            icon={<NotebookPen size={16} />}
            label={t("items.notebooks")}
            onClick={() => navigate("/notebooks")}
          />
          <NavRow
            icon={<FolderTree size={16} />}
            label={t("items.files")}
            onClick={() => navigate("/files")}
          />
          <NavRow
            icon={<FlaskConical size={16} />}
            label={t("items.runs")}
            onClick={() => navigate("/runs")}
          />
          <NavRow
            icon={<Files size={16} />}
            label={t("items.skills")}
            onClick={() => navigate("/skills")}
          />
        </nav>

        <div className="mt-4 flex-1 overflow-y-auto px-3 pb-2">
          <div className="flex items-center justify-between px-2 py-1">
            <span className="text-xs font-medium uppercase tracking-wider text-muted">
              {t("projects.heading")}
            </span>
            <button
              onClick={() => setCreatingProject(true)}
              aria-label={t("projects.new")}
              title={t("projects.new")}
              className="rounded p-0.5 text-muted hover:bg-surface-2 hover:text-text"
            >
              <Plus size={13} />
            </button>
          </div>
          {creatingProject && (
            <div className="px-1 pb-1">
              <InlineNameInput
                placeholder={t("projects.namePlaceholder")}
                busy={createBusy}
                onSubmit={(v) => void submitNewProject(v)}
                onCancel={() => {
                  if (!createBusy) setCreatingProject(false);
                }}
              />
            </div>
          )}
          {projects.length === 0 && !creatingProject && (
            <button
              onClick={() => setCreatingProject(true)}
              className="flex w-full items-center gap-2 rounded-input px-2 py-1 text-[13px] text-muted hover:bg-surface-2 hover:text-text"
            >
              <Folder size={14} className="shrink-0" />
              <span className="truncate">{t("projects.new")}</span>
            </button>
          )}
          {projects.map((p) => {
            const open = !collapsedProjects.includes(p.id);
            const active = p.path === workspace;
            const rows = sessionsByProject.get(p.id) ?? [];
            return (
              <div key={p.id}>
                {renamingId === p.id ? (
                  <div className="py-0.5 pl-5 pr-1">
                    <InlineNameInput
                      defaultValue={p.name}
                      placeholder={t("projects.namePlaceholder")}
                      onSubmit={(v) => void submitRename(p, v)}
                      onCancel={() => setRenamingId(null)}
                    />
                  </div>
                ) : (
                  <div className="group/project relative">
                    <button
                      onClick={() => toggleProject(p.id)}
                      aria-expanded={open}
                      className="flex w-full items-center gap-1.5 rounded-input py-1 pl-1 pr-10 text-[13px] text-text hover:bg-surface-2"
                    >
                      <ChevronRight
                        size={11}
                        className={cn(
                          "shrink-0 text-muted transition-transform duration-150",
                          open && "rotate-90",
                        )}
                      />
                      {open ? (
                        <FolderOpen
                          size={14}
                          className={cn(
                            "shrink-0",
                            active ? "text-accent" : "text-muted",
                          )}
                        />
                      ) : (
                        <Folder
                          size={14}
                          className={cn(
                            "shrink-0",
                            active ? "text-accent" : "text-muted",
                          )}
                        />
                      )}
                      <span
                        className="min-w-0 flex-1 truncate text-left font-medium"
                        onDoubleClick={(e) => {
                          e.stopPropagation();
                          setRenamingId(p.id);
                        }}
                        title={t("projects.renameHint")}
                      >
                        {p.name}
                      </span>
                    </button>
                    <div className="absolute right-1.5 top-1/2 flex -translate-y-1/2 items-center">
                      {rows.length > 0 && (
                        <span className="px-1 text-[10px] tabular-nums text-muted group-hover/project:hidden">
                          {rows.length}
                        </span>
                      )}
                      <button
                        onClick={() => void newSessionIn(p)}
                        aria-label={t("projects.newSessionAria", {
                          name: p.name,
                        })}
                        title={t("projects.newSessionAria", { name: p.name })}
                        className="hidden rounded p-1 text-muted hover:bg-border hover:text-text group-hover/project:block"
                      >
                        <Plus size={13} />
                      </button>
                    </div>
                  </div>
                )}
                <div
                  className={cn(
                    "grid transition-[grid-template-rows] duration-200 ease-out",
                    open ? "grid-rows-[1fr]" : "grid-rows-[0fr]",
                  )}
                >
                  <div className="overflow-hidden">
                    <div className="mb-0.5 ml-[15px] border-l border-border-faint pl-1.5">
                      {rows.length === 0 && (
                        <div className="px-2 py-1 text-xs text-muted">
                          {t("projects.noSessions")}
                        </div>
                      )}
                      {rows.map(sessionRow)}
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
          <div className="mt-3 px-2 py-1 text-xs font-medium uppercase tracking-wider text-muted">
            {t("history.heading")}
          </div>
          {looseRows.length === 0 && exampleRows.length === 0 && (
            <div className="px-2 py-2 text-xs text-muted">
              {t("history.empty")}
            </div>
          )}
          {looseRows.map(sessionRow)}
          {exampleRows.map(sessionRow)}
        </div>

        <div className="border-t border-border px-3 py-3">
          <StatusPills />
          <button
            className="relative mt-2 flex items-center gap-2 rounded-input px-2 py-1 text-[13px] text-muted hover:bg-surface-2 hover:text-text"
            onClick={() => navigate("/settings")}
            aria-label={t("sidebar.settings")}
          >
            <Settings size={15} />
            <span>{t("sidebar.settings")}</span>
            {showUpdateBadge && (
              <span
                aria-hidden="true"
                className="ml-auto h-2 w-2 rounded-full bg-error shadow-[0_0_0_2px_var(--color-surface)]"
              />
            )}
          </button>
        </div>

        {pendingDelete && (
          <ConfirmDialog
            title={
              pendingDelete.kind === "session"
                ? t("confirmDelete.sessionTitle")
                : t("confirmDelete.exampleTitle")
            }
            body={
              pendingDelete.kind === "session"
                ? t("confirmDelete.sessionBody", { title: pendingDelete.title })
                : t("confirmDelete.exampleBody", { title: pendingDelete.title })
            }
            confirmLabel={
              pendingDelete.kind === "session"
                ? t("confirmDelete.deleteAction")
                : t("confirmDelete.hideAction")
            }
            onConfirm={confirmDelete}
            onCancel={() => setPendingDelete(null)}
          />
        )}
      </aside>

      {/* Drag divider: resize within [SIDEBAR_MIN, SIDEBAR_MAX]; dragging far
          left snaps the sidebar closed. Kept mounted while collapsed so an
          in-flight drag (pointer capture) can re-open it. */}
      <div
        onPointerDown={onDividerPointerDown}
        onPointerMove={onDividerPointerMove}
        onPointerUp={onDividerPointerUp}
        onPointerCancel={onDividerPointerUp}
        className={cn(
          "group absolute inset-y-0 right-0 z-10 w-[5px] cursor-col-resize",
          sidebarCollapsed && !dragging && "pointer-events-none",
        )}
      >
        <div
          className={cn(
            "absolute inset-y-0 right-0 w-[2px] transition-colors",
            dragging
              ? "bg-accent/60"
              : "bg-transparent group-hover:bg-accent/40",
          )}
        />
      </div>
    </div>
  );
}

function NavRow({
  icon,
  label,
  onClick,
  active = false,
}: {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
  active?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "flex items-center gap-2 rounded-input px-2 py-1 text-[13px] text-text hover:bg-surface-2",
        active && "bg-surface-2",
      )}
    >
      <span className={active ? "text-accent" : "text-muted"}>{icon}</span>
      <span>{label}</span>
    </button>
  );
}

/** One-line name editor used for "new project" and rename: Enter submits,
 *  Escape or clicking away cancels — no dialog, the row edits in place. */
function InlineNameInput({
  defaultValue = "",
  placeholder,
  busy = false,
  onSubmit,
  onCancel,
}: {
  defaultValue?: string;
  placeholder?: string;
  busy?: boolean;
  onSubmit: (value: string) => void;
  onCancel: () => void;
}) {
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => {
    ref.current?.focus();
    ref.current?.select();
  }, []);
  return (
    <input
      ref={ref}
      defaultValue={defaultValue}
      placeholder={placeholder}
      disabled={busy}
      onKeyDown={(e) => {
        if (e.key === "Enter") onSubmit(e.currentTarget.value);
        else if (e.key === "Escape") onCancel();
      }}
      onBlur={() => {
        if (!busy) onCancel();
      }}
      className={cn(
        "w-full min-w-0 rounded-input border border-accent/50 bg-surface px-2 py-[3px] text-[13px] text-text outline-none placeholder:text-muted focus:border-accent",
        busy && "animate-pulse opacity-60",
      )}
    />
  );
}
