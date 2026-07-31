import { useState } from "react";
import { Check, HelpCircle, Info, ShieldQuestion } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { PermissionAskedEvent, PermissionReply, QuestionAskedEvent } from "@ai4s/sdk";
import { cn } from "@/lib/cn";

/**
 * The answerable surface for an agent request that blocks the run — a
 * `question` (pick options) or a `permission` (approve an action). Without
 * this, the agent's `question`/`permission` tool sits forever and the session
 * looks stuck. Rendered just above the composer for the current session.
 */
export function InteractionPrompt({
  question,
  permission,
  origin,
  onAnswer,
  onReject,
  onPermission,
}: {
  question?: QuestionAskedEvent;
  permission?: PermissionAskedEvent;
  /** Who is asking, when it isn't the main agent — a subagent session's title. */
  origin?: string;
  onAnswer: (requestId: string, answers: string[][]) => void;
  onReject: (requestId: string) => void;
  onPermission: (requestId: string, reply: PermissionReply) => void;
}) {
  if (question) {
    return (
      <QuestionCard
        key={question.requestId}
        question={question}
        origin={origin}
        onAnswer={onAnswer}
        onReject={onReject}
      />
    );
  }
  if (permission) {
    return (
      <PermissionCard
        key={permission.requestId}
        permission={permission}
        origin={origin}
        onReply={onPermission}
      />
    );
  }
  return null;
}

/** "external_directory" → "external directory" — readable, still explicit. */
const actionLabel = (action: string) => action.replace(/[_-]+/g, " ");

// Question options are tool arguments authored by the active model, not app
// copy. Keep the raw event in runtime state for audit, but do not render an
// obviously corrupted description as if it were a meaningful Human choice.
const repeatedPunctuation = /([\\`~|,，、.。;；:：'"“”‘’])(?:\s*\1){7,}/u;
const usableOptionDescription = (value?: string) => (
  Boolean(value?.trim()) && value!.length <= 2_000 && !repeatedPunctuation.test(value!)
);

// Option explanations must be understandable inside this card. A reference to
// a table or figure that is not rendered here is missing context, not useful
// decision support.
const missingVisibleContext = /(?:上面(?:的)?(?:表格|表|图|图表)|上表|上图|下表|下图|(?:the\s+)?(?:table|figure|chart)\s+(?:above|below)|above\s+(?:table|figure|chart)|below\s+(?:table|figure|chart)|(?:obige|nachstehende)\s+tabelle|tabla\s+(?:anterior|de\s+arriba)|tableau\s+ci-dessus|上の表|上の図|위\s*표|위\s*그림)/iu;
const referencesMissingVisibleContext = (value?: string) => (
  Boolean(value?.trim()) && missingVisibleContext.test(value!)
);

// A question event is authored by the active model. For medicine identity and
// regulatory facts, its options are not evidence and can silently turn a
// hallucination into an apparently authoritative Human choice. Keep the raw
// event in runtime state for audit, but require a sourced open answer here.
const medicineFactQuestion = /(?:适应症|获批|批准用于|说明书|注册状态|药品通用名|活性成分|上市许可持有人|approved\s+indication|marketing\s+authori[sz]ation|product\s+label|package\s+insert|active\s+ingredient)/iu;
const publicPriceQuestion = /(?:药品价格|药价|价格表|挂网价|中标价|采购价|集采价|医保支付标准|list\s+price|tender\s+price|procurement\s+price|acquisition\s+cost|reimbursement\s+(?:price|rate))/iu;
const unverifiedCitationOption = /(?:PMID\s*[:#]?\s*\d+|DOI\s*[:#]?\s*10\.\d{4,9}\/|NCT\d{8})/iu;
const publicSourceLocator = /https?:\/\/[^\s)）]+/iu;
const retrievalDate = /(?:(?:检索|访问|获取)日期|retriev(?:ed|al)(?:\s+date)?|accessed)(?:\s*(?:on|于))?\s*[:：]?\s*\d{4}-\d{2}-\d{2}/iu;
const hasTraceablePublicSource = (description?: string) => (
  Boolean(description?.trim())
  && publicSourceLocator.test(description!)
  && retrievalDate.test(description!)
);
export const requiresSourcedOpenAnswer = (
  header: string,
  question: string,
  optionText = "",
  everyOptionHasTraceableSource = false,
) => {
  const content = `${header}\n${question}\n${optionText}`;
  const asksForPublicFact = medicineFactQuestion.test(content)
    || publicPriceQuestion.test(content)
    || unverifiedCitationOption.test(optionText);
  return asksForPublicFact && !everyOptionHasTraceableSource;
};

function QuestionCard({
  question,
  origin,
  onAnswer,
  onReject,
}: {
  question: QuestionAskedEvent;
  origin?: string;
  onAnswer: (requestId: string, answers: string[][]) => void;
  onReject: (requestId: string) => void;
}) {
  const { t } = useTranslation(["session", "common"]);
  // One selection set + one custom string per question.
  const [selected, setSelected] = useState<Record<number, Set<string>>>({});
  const [custom, setCustom] = useState<Record<number, string>>({});

  const items = question.questions;
  const openAnswerOnly = items.map((item) => requiresSourcedOpenAnswer(
    item.header,
    item.question,
    item.options.map((option) => `${option.label}\n${option.description ?? ""}`).join("\n"),
    item.options.length > 0 && item.options.every((option) => hasTraceablePublicSource(option.description)),
  ));
  const toggle = (qi: number, label: string, multiple: boolean) =>
    setSelected((s) => {
      const cur = new Set(multiple ? (s[qi] ?? []) : []);
      if (cur.has(label)) cur.delete(label);
      else cur.add(label);
      return { ...s, [qi]: cur };
    });

  const answerFor = (qi: number): string[] => {
    const picked = openAnswerOnly[qi] ? [] : [...(selected[qi] ?? [])];
    const c = custom[qi]?.trim();
    return c ? [c] : picked;
  };
  const ready = items.every((_, qi) => answerFor(qi).length > 0);

  return (
    <div className="rounded-card border border-accent/40 bg-surface shadow-card">
      <header className="border-b border-border px-4 py-2.5">
        <div className="flex items-center gap-2">
          <HelpCircle size={15} className="text-accent" />
          <span className="text-sm font-medium text-text">{t("interaction.question.heading")}</span>
        </div>
        {origin && (
          <div className="mt-0.5 pl-6 text-xs text-muted">{t("interaction.askedBy", { origin })}</div>
        )}
      </header>

      <div className="max-h-[45vh] space-y-4 overflow-y-auto px-4 py-3.5">
        {items.map((it, qi) => {
          const multiple = !!it.multiple;
          const requiresSource = openAnswerOnly[qi];
          const inputId = `question-${question.requestId}-${qi}`;
          const helpId = `${inputId}-help`;
          return (
            <div key={qi} className="space-y-2">
              <label htmlFor={inputId} className="block text-sm text-text">
                {it.question}
              </label>
              {requiresSource && (
                <p
                  id={helpId}
                  className="flex items-start gap-1.5 px-0.5 text-xs leading-relaxed text-muted"
                >
                  <Info size={13} className="mt-0.5 shrink-0 text-warn" aria-hidden={true} />
                  <span>{t("interaction.question.sourcedMedicineFact")}</span>
                </p>
              )}
              {!requiresSource && <div className="flex flex-col gap-1.5">
                {it.options.map((opt) => {
                  const on = selected[qi]?.has(opt.label) ?? false;
                  const descriptionUsable = usableOptionDescription(opt.description);
                  const missingContext = referencesMissingVisibleContext(opt.description);
                  return (
                    <button
                      key={opt.label}
                      onClick={() => {
                        setCustom((c) => ({ ...c, [qi]: "" }));
                        toggle(qi, opt.label, multiple);
                      }}
                      className={cn(
                        "flex items-start gap-2.5 rounded-input border px-3 py-2 text-left transition-colors",
                        on
                          ? "border-accent bg-accent/10"
                          : "border-border bg-surface hover:bg-surface-2",
                      )}
                    >
                      <span
                        className={cn(
                          "mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded-full border",
                          on ? "border-accent bg-accent text-accent-fg" : "border-muted/50",
                        )}
                      >
                        {on && <Check size={11} strokeWidth={3} />}
                      </span>
                      <span className="min-w-0">
                        <span className="block text-[13px] font-medium text-text">{opt.label}</span>
                        {descriptionUsable && !missingContext && (
                          <span className="mt-0.5 block text-xs leading-snug text-muted">
                            {opt.description}
                          </span>
                        )}
                        {opt.description && missingContext && (
                          <span className="mt-0.5 block text-xs leading-snug text-warn">
                            {t("interaction.question.missingContextDescription")}
                          </span>
                        )}
                        {opt.description && !descriptionUsable && !missingContext && (
                          <span className="mt-0.5 block text-xs leading-snug text-warn">
                            {t("interaction.question.invalidDescription")}
                          </span>
                        )}
                      </span>
                    </button>
                  );
                })}
              </div>}
              <div className="space-y-1.5">
                <p className="px-0.5 text-xs text-muted">
                  {t(requiresSource
                    ? "interaction.question.sourcedAnswerLabel"
                    : "interaction.question.customLabel")}
                </p>
                <input
                  id={inputId}
                  aria-describedby={requiresSource ? helpId : undefined}
                  value={custom[qi] ?? ""}
                  onChange={(e) => {
                    const value = e.target.value;
                    setCustom((c) => ({ ...c, [qi]: value }));
                    if (value.trim()) {
                      setSelected((s) => ({ ...s, [qi]: new Set() }));
                    }
                  }}
                  placeholder={t(requiresSource
                    ? "interaction.question.sourcedAnswerPlaceholder"
                    : "interaction.question.customPlaceholder")}
                  className="w-full rounded-input border border-border bg-surface px-3 py-2 text-[13px] text-text outline-none placeholder:text-muted focus:border-accent/60"
                />
              </div>
            </div>
          );
        })}
      </div>

      <footer className="flex justify-end gap-2 border-t border-border px-4 py-2.5">
        <button
          className="rounded-input px-3 py-1.5 text-xs text-muted hover:text-text"
          onClick={() => onReject(question.requestId)}
        >
          {t("interaction.skip")}
        </button>
        <button
          disabled={!ready}
          onClick={() => onAnswer(question.requestId, items.map((_, qi) => answerFor(qi)))}
          className="rounded-input bg-accent px-3.5 py-1.5 text-xs font-medium text-accent-fg hover:opacity-90 disabled:opacity-40"
        >
          {t("interaction.submit")}
        </button>
      </footer>
    </div>
  );
}

function PermissionCard({
  permission,
  origin,
  onReply,
}: {
  permission: PermissionAskedEvent;
  origin?: string;
  onReply: (requestId: string, reply: PermissionReply) => void;
}) {
  const { t } = useTranslation(["session", "common"]);
  return (
    <div className="rounded-card border border-warn/40 bg-surface shadow-card">
      <header className="border-b border-border px-4 py-2.5">
        <div className="flex items-center gap-2">
          <ShieldQuestion size={15} className="text-warn" />
          <span className="text-sm font-medium text-text">
            {t("interaction.permission.heading")}{" "}
            <span className="font-mono">{actionLabel(permission.action)}</span>
          </span>
        </div>
        {origin && (
          <div className="mt-0.5 pl-6 text-xs text-muted">{t("interaction.askedBy", { origin })}</div>
        )}
      </header>
      {permission.resources.length > 0 && (
        <div className="px-4 py-3">
          <pre className="max-h-40 overflow-auto whitespace-pre-wrap rounded-input border border-border bg-surface-2 px-3 py-2 font-mono text-[12px] text-text">
            {permission.resources.join("\n")}
          </pre>
          <p className="mt-2 text-xs leading-relaxed text-muted">
            {t("interaction.permission.alwaysScope")}
          </p>
        </div>
      )}
      <footer className="flex items-center gap-2 border-t border-border px-4 py-2.5">
        <button
          className="rounded-input px-3 py-1.5 text-xs text-error hover:bg-error/10"
          onClick={() => onReply(permission.requestId, "reject")}
        >
          {t("interaction.reject")}
        </button>
        <div className="flex-1" />
        <button
          className="rounded-input border border-border px-3 py-1.5 text-xs text-text hover:bg-surface-2"
          onClick={() => onReply(permission.requestId, "always")}
        >
          {t("interaction.alwaysAllow")}
        </button>
        <button
          className="rounded-input bg-accent px-3.5 py-1.5 text-xs font-medium text-accent-fg hover:opacity-90"
          onClick={() => onReply(permission.requestId, "once")}
        >
          {t("interaction.allowOnce")}
        </button>
      </footer>
    </div>
  );
}
