import { useCallback, useEffect, useState } from "react";
import { Loader2, RotateCcw, ShieldCheck } from "lucide-react";
import type { SavedPermission } from "@ai4s/sdk";
import { useTranslation } from "react-i18next";
import { Section } from "./Section";

type SavedPermissionClient = {
  listSavedPermissions: (directory?: string) => Promise<SavedPermission[]>;
  removeSavedPermission: (id: string, directory?: string) => Promise<void>;
};

export function SavedPermissionsCard({
  connected,
  workspace,
  client,
}: {
  connected: boolean;
  workspace: string | null;
  client: SavedPermissionClient | null;
}) {
  const { t } = useTranslation("settings");
  const [items, setItems] = useState<SavedPermission[]>([]);
  const [loading, setLoading] = useState(false);
  const [removing, setRemoving] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  const load = useCallback(async () => {
    if (!connected || !client) {
      setItems([]);
      setFailed(false);
      return;
    }
    setLoading(true);
    setFailed(false);
    try {
      setItems(await client.listSavedPermissions(workspace ?? undefined));
    } catch {
      setFailed(true);
    } finally {
      setLoading(false);
    }
  }, [client, connected, workspace]);

  useEffect(() => {
    void load();
  }, [load]);

  const remove = async (id: string) => {
    if (!client) return;
    setRemoving(id);
    try {
      await client.removeSavedPermission(id, workspace ?? undefined);
      await load();
    } catch {
      setFailed(true);
    } finally {
      setRemoving(null);
    }
  };

  return (
    <Section title={t("savedPermissions.title")} hint={t("savedPermissions.hint")} flush>
      {!connected || !client ? (
        <p className="px-4 py-3 text-xs text-muted">{t("savedPermissions.connect")}</p>
      ) : loading && items.length === 0 ? (
        <div className="flex items-center gap-2 px-4 py-3 text-xs text-muted">
          <Loader2 size={13} className="animate-spin" />
          {t("savedPermissions.loading")}
        </div>
      ) : failed ? (
        <div className="flex items-center justify-between gap-4 px-4 py-3">
          <p className="text-xs text-error">{t("savedPermissions.failed")}</p>
          <button
            type="button"
            className="inline-flex items-center gap-1.5 rounded-input border border-border px-2.5 py-1.5 text-xs text-text hover:bg-surface-2"
            onClick={() => void load()}
          >
            <RotateCcw size={12} />
            {t("savedPermissions.retry")}
          </button>
        </div>
      ) : items.length === 0 ? (
        <div className="flex items-center gap-2 px-4 py-3 text-xs text-muted">
          <ShieldCheck size={14} />
          {t("savedPermissions.empty")}
        </div>
      ) : (
        <div className="divide-y divide-border">
          {items.map((item) => (
            <div key={item.id} className="flex items-center gap-4 px-4 py-3">
              <div className="min-w-0 flex-1">
                <div className="text-xs font-medium text-text">{item.action}</div>
                <div className="mt-1 break-all font-mono text-[11px] leading-relaxed text-muted">
                  {item.resource}
                </div>
              </div>
              <button
                type="button"
                data-testid="saved-permission-revoke"
                className="shrink-0 rounded-input border border-border px-2.5 py-1.5 text-xs text-text hover:bg-surface-2 disabled:opacity-50"
                disabled={removing === item.id}
                onClick={() => void remove(item.id)}
              >
                {removing === item.id ? t("savedPermissions.removing") : t("savedPermissions.revoke")}
              </button>
            </div>
          ))}
        </div>
      )}
    </Section>
  );
}
