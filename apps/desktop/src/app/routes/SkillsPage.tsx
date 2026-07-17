import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Bot, Boxes, Check, Package, Puzzle, ShieldCheck, X } from "lucide-react";
import { useRuntimeStore } from "@/lib/runtime";
import { cn } from "@/lib/cn";
import { localizeSkill } from "@/i18n/skillLocalization";
import { auditAssetAdmission, type AssetAdmissionAudit, type AssetAdmissionRecord } from "@/lib/tauri";

/**
 * Runtime capabilities plus the app-owned third-party admission registry.
 * Natural-language review is the primary external-asset workflow; the registry
 * is the secondary, deterministic release control.
 */
export function SkillsPage() {
  const { t, i18n } = useTranslation(["pages", "common", "skills"]);
  const navigate = useNavigate();
  const { skills, agents, tools, status, loadCatalog, detectTools, reviewAssetCandidate } = useRuntimeStore();
  const connected = status === "ready";
  const [text, setText] = useState("");
  const [reviewing, setReviewing] = useState(false);
  const [admission, setAdmission] = useState<AssetAdmissionAudit | null>(null);
  const [admissionError, setAdmissionError] = useState(false);

  useEffect(() => {
    if (connected) void loadCatalog();
    void detectTools();
  }, [connected, loadCatalog, detectTools]);

  useEffect(() => {
    let current = true;
    void auditAssetAdmission()
      .then((result) => {
        if (current) setAdmission(result);
      })
      .catch(() => {
        if (current) setAdmissionError(true);
      });
    return () => {
      current = false;
    };
  }, []);

  const onReview = async () => {
    if (!text.trim()) return;
    setReviewing(true);
    const id = await reviewAssetCandidate(text.trim());
    setReviewing(false);
    if (id) {
      setText("");
      navigate(`/live/${id}`); // watch the agent install it
    }
  };

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-3xl px-8 py-8">
        <h1 className="font-serif text-xl text-text">{t("skills.title")}</h1>
        <p className="mt-1 text-sm text-muted">
          {t("skills.description.prefix")}
          {/* eslint-disable-next-line i18next/no-literal-string -- literal filesystem path, not prose */}
          <span className="font-mono">.opencode/skills/</span>
          {t("skills.description.suffix")}
        </p>

        {/* Natural-language work first: review and adapt, never install directly. */}
        <Section title={t("skills.install.sectionTitle")} icon={<Boxes size={15} />}>
          <div className="p-4">
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder={t("skills.install.placeholder")}
              rows={3}
              className="w-full resize-y rounded-input border border-border bg-surface px-3 py-2 text-sm text-text outline-none placeholder:text-muted"
            />
            <div className="mt-2 flex items-center gap-3">
              <button
                onClick={onReview}
                disabled={!connected || !text.trim() || reviewing}
                className="rounded-input bg-accent px-3 py-1.5 text-sm font-medium text-accent-fg hover:opacity-90 disabled:opacity-40"
              >
                {reviewing ? t("skills.install.starting") : t("skills.install.cta")}
              </button>
              <span className="text-xs text-muted">
                {connected ? t("skills.install.hintConnected") : t("skills.install.hintDisconnected")}
              </span>
            </div>
          </div>
        </Section>

        <Section title={t("skills.assetAdmission.sectionTitle")} icon={<ShieldCheck size={15} />}>
          {admissionError && <Empty>{t("skills.assetAdmission.unavailable")}</Empty>}
          {!admission && !admissionError && <Empty>{t("skills.assetAdmission.loading")}</Empty>}
          {admission && (
            <>
              <div className="grid grid-cols-3 gap-px bg-border">
                <AdmissionCount value={admission.admittedCount} label={t("skills.assetAdmission.admitted")} />
                <AdmissionCount value={admission.quarantinedCount} label={t("skills.assetAdmission.quarantined")} />
                <AdmissionCount value={admission.rejectedCount} label={t("skills.assetAdmission.rejected")} />
              </div>
              <p className={cn("px-4 py-3 text-xs", admission.complete ? "text-muted" : "text-danger") }>
                {admission.complete
                  ? admission.admittedCount === 0
                    ? t("skills.assetAdmission.noneAdmitted")
                    : t("skills.assetAdmission.registryValid", { count: admission.admittedCount })
                  : t("skills.assetAdmission.failClosed")}
              </p>
              {admission.errors.map((error) => (
                <div key={error} className="px-4 py-2 text-xs text-danger">{error}</div>
              ))}
              {admission.assets.map((asset) => <AdmissionRow key={asset.assetId} asset={asset} />)}
            </>
          )}
        </Section>

        {/* Environment (#2) */}
        <Section title={t("skills.environment.sectionTitle")} icon={<Package size={15} />}>
          {tools.length === 0 && <Empty>{t("skills.environment.detectionUnavailable")}</Empty>}
          {tools.map((tool) => (
            <div key={tool.name} className="flex items-center gap-3 px-4 py-2.5 text-sm">
              {tool.found ? <Check size={15} className="text-ok" /> : <X size={15} className="text-muted" />}
              <span className="w-24 text-text">{tool.name}</span>
              <span className="flex-1 truncate font-mono text-xs text-muted">
                {tool.found ? tool.version ?? t("skills.environment.found") : t("skills.environment.notFound")}
              </span>
            </div>
          ))}
          <p className="px-4 py-2 text-xs text-muted">{t("skills.environment.note")}</p>
        </Section>

        {connected ? (
          <>
            <Section title={t("skills.agentsSection.sectionTitle", { count: agents.length })} icon={<Bot size={15} />}>
              {agents.length === 0 && <Empty>{t("skills.agentsSection.empty")}</Empty>}
              {agents.map((a) => {
                const mode = modeOf(a.mode);
                const modeLabel = mode ? t(`skills.agentsSection.agentMode.${mode}`) : a.mode;
                return <RowItem key={a.name} name={a.name} desc={a.description} tag={modeLabel} />;
              })}
            </Section>
            <Section title={t("skills.skillsListSection.sectionTitle", { count: skills.length })} icon={<Puzzle size={15} />}>
              {skills.length === 0 && <Empty>{t("skills.skillsListSection.empty")}</Empty>}
              {skills.map((s) => {
                const copy = localizeSkill(s.name, s.description, i18n.resolvedLanguage);
                const source = sourceOf(s.location);
                const sourceLabel =
                  source === "builtin"
                    ? t("skills.skillsListSection.source.builtin")
                    : source === "project"
                      ? t("skills.skillsListSection.source.project")
                      : source === "bundled"
                        ? t("skills.skillsListSection.source.bundled")
                        : undefined;
                return (
                  <RowItem
                    key={s.name}
                    name={copy.displayName}
                    code={copy.localized ? `$${s.name}` : undefined}
                    desc={copy.description}
                    tag={sourceLabel}
                  />
                );
              })}
            </Section>
          </>
        ) : (
          <div className="mt-6 rounded-card border border-border bg-surface p-5 text-sm text-muted">
            {t("skills.disconnected")}
          </div>
        )}
      </div>
    </div>
  );
}

type SkillSource = "builtin" | "project" | "bundled";

function sourceOf(location?: string): SkillSource | undefined {
  if (!location) return undefined;
  const normalized = location.split("\\").join("/");
  if (normalized.includes("/builtin/")) return "builtin";
  if (normalized.includes("/.opencode/")) return "project";
  return "bundled";
}

// AgentInfo.mode is typed `string` (external SDK), but OpenCode only ever
// emits "primary" | "subagent" | "all" — see useRuntimeStore's a.mode ===
// "primary" check. Narrow to the known set so we can translate it; unknown
// values (future SDK additions) fall back to the raw string at the call site.
type AgentMode = "primary" | "subagent" | "all";

function modeOf(mode?: string): AgentMode | undefined {
  return mode === "primary" || mode === "subagent" || mode === "all" ? mode : undefined;
}

function Section({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="mt-6">
      <h2 className="mb-2 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wider text-muted">
        {icon} {title}
      </h2>
      <div className="divide-y divide-border overflow-hidden rounded-card border border-border bg-surface">
        {children}
      </div>
    </section>
  );
}

function RowItem({ name, desc, tag, code }: { name: string; desc: string; tag?: string; code?: string }) {
  return (
    <div className="flex items-start gap-3 px-4 py-3">
      <Package size={16} className="mt-0.5 shrink-0 text-muted" />
      <div className="min-w-0 flex-1">
        <div className="flex min-w-0 items-baseline gap-2">
          <div className="truncate text-sm font-medium text-text">{name}</div>
          {code && <span className="truncate font-mono text-[10.5px] text-muted">{code}</span>}
        </div>
        <div className={cn("text-xs text-muted", "line-clamp-2")}>{desc}</div>
      </div>
      {tag && (
        <span className="shrink-0 rounded-full bg-surface-2 px-2 py-0.5 text-xs text-muted ring-1 ring-border">
          {tag}
        </span>
      )}
    </div>
  );
}

function AdmissionCount({ value, label }: { value: number; label: string }) {
  return (
    <div className="bg-surface px-4 py-3 text-center">
      <div className="font-mono text-lg font-semibold text-text">{value}</div>
      <div className="text-xs text-muted">{label}</div>
    </div>
  );
}

function AdmissionRow({ asset }: { asset: AssetAdmissionRecord }) {
  const { t } = useTranslation("pages");
  const status = admissionStatus(asset.status);
  const label = status ? t(`skills.assetAdmission.status.${status}`) : asset.status;
  return (
    <div className="flex items-start gap-3 px-4 py-3">
      {asset.status === "validated-adapter" ? (
        <Check size={16} className="mt-0.5 shrink-0 text-ok" />
      ) : (
        <X size={16} className={cn("mt-0.5 shrink-0", asset.status === "rejected" ? "text-danger" : "text-muted")} />
      )}
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium text-text">{asset.displayName}</span>
          <span className="rounded-full bg-surface-2 px-2 py-0.5 text-xs text-muted ring-1 ring-border">{label}</span>
          <span className="font-mono text-[11px] text-muted">{asset.licenseSpdx}</span>
        </div>
        <div className="mt-1 line-clamp-2 text-xs text-muted">
          {asset.blockers[0] ?? t("skills.assetAdmission.noBlockers")}
        </div>
      </div>
    </div>
  );
}

type AdmissionStatus = "admitted" | "quarantined" | "rejected";

function admissionStatus(status: string): AdmissionStatus | undefined {
  if (status === "validated-adapter") return "admitted";
  if (status === "quarantined" || status === "rejected") return status;
  return undefined;
}

function Empty({ children }: { children: React.ReactNode }) {
  return <div className="px-4 py-6 text-center text-sm text-muted">{children}</div>;
}
