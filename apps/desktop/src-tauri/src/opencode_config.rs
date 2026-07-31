// Pure OpenCode permission configuration used by the runtime command layer.
use serde_json::{json, Value};
use std::path::Path;

/// Approval modes for agent tool use (the composer's Codex-style switch).
/// OpenCode evaluates permission rules last-match-wins with user config rules
/// appended after its builtin `"*": "allow"` — so "approve" only needs `ask`
/// rules and everything unmatched still runs without a prompt.
pub const MODE_APPROVE: &str = "approve";
pub const MODE_FULL: &str = "full";

/// Command tokens the "approve" mode gates behind a prompt, per the AGENTS.md
/// safety defaults: deletion, privilege/system changes, dependency installs,
/// and remote/outward connections. Each token yields two glob rules:
/// `"T *"` (command starts with it; also matches bare `T` — OpenCode turns a
/// trailing " *" into an optional group) and `"* T *"` (embedded in a compound
/// command like `cd x && rm -rf y`; the leading space avoids matching words
/// that merely end in the token).
const DANGEROUS_BASH: &[&str] = &[
    // deletion
    "rm",
    "rmdir",
    "shred",
    "git clean",
    // privilege / system state
    "sudo",
    "su",
    "chmod",
    "chown",
    "kill",
    "pkill",
    "killall",
    "launchctl",
    "systemctl",
    "crontab",
    "osascript",
    "diskutil",
    "dd",
    // dependency installs
    "pip install",
    "pip3 install",
    "uv add",
    "uv pip install",
    "npm install",
    "npm i",
    "pnpm add",
    "pnpm install",
    "yarn add",
    "conda install",
    "mamba install",
    "brew install",
    "cargo install",
    "gem install",
    "apt install",
    "apt-get install",
    // remote / outward
    "ssh",
    "scp",
    "sftp",
    "rsync",
    "curl",
    "wget",
    "nc",
    "git push",
    "modal",
    "sbatch",
];

/// Build the per-process OpenCode config that guarantees the verified,
/// app-owned product Harness is loaded in addition to project/user
/// instructions. This is intentionally ephemeral: imported project files and
/// the user's persisted OpenCode config remain byte-for-byte unchanged.
pub fn product_harness_config_content(
    inherited: Option<&str>,
    product_agents_path: &Path,
) -> Result<String, String> {
    if !product_agents_path.is_absolute() {
        return Err("product Harness instruction path must be absolute".into());
    }
    let product_path = product_agents_path.to_string_lossy().replace('\\', "/");
    if product_path.is_empty() {
        return Err("product Harness instruction path is empty".into());
    }

    let inherited = inherited.unwrap_or_default();
    let mut root: Value = if inherited.trim().is_empty() {
        json!({})
    } else {
        serde_json::from_str(inherited)
            .map_err(|error| format!("invalid inherited OpenCode config: {error}"))?
    };
    let object = root
        .as_object_mut()
        .ok_or("inherited OpenCode config must be a JSON object")?;
    let instructions = object
        .entry("instructions")
        .or_insert_with(|| json!([]))
        .as_array_mut()
        .ok_or("inherited OpenCode instructions must be an array")?;
    if instructions.iter().any(|value| !value.is_string()) {
        return Err("inherited OpenCode instructions must contain only strings".into());
    }
    instructions.retain(|value| value.as_str() != Some(product_path.as_str()));
    instructions.push(json!(product_path));

    serde_json::to_string_pretty(&root).map_err(|error| error.to_string())
}

fn approve_permission() -> Value {
    let mut bash = serde_json::Map::new();
    for t in DANGEROUS_BASH {
        bash.insert(format!("{t} *"), json!("ask"));
        bash.insert(format!("* {t} *"), json!("ask"));
    }
    json!({ "bash": Value::Object(bash), "webfetch": "ask" })
}

/// Set the approval mode in OpenCode config JSON. "approve" installs the ask
/// rules; "full" writes an explicit allow-all rule. An empty object is not
/// equivalent: OpenCode still applies builtin prompts such as
/// `external_directory`, which can leave an unattended test task stuck in a
/// generic "running" state. The key's presence also marks that the user made
/// a choice (so startup seeding never overrides it). Other keys are preserved.
pub fn set_permission_mode(existing: &str, mode: &str) -> Result<String, String> {
    let permission = match mode {
        MODE_APPROVE => approve_permission(),
        MODE_FULL => json!({ "*": "allow" }),
        other => return Err(format!("unknown approval mode \"{other}\"")),
    };
    let mut root: Value = if existing.trim().is_empty() {
        json!({})
    } else {
        serde_json::from_str(existing).map_err(|e| format!("invalid existing config: {e}"))?
    };
    if !root.is_object() {
        root = json!({});
    }
    root.as_object_mut()
        .unwrap()
        .insert("permission".to_string(), permission);
    serde_json::to_string_pretty(&root).map_err(|e| e.to_string())
}

/// Seed the "approve" default on first run (no `permission` key yet). Also
/// migrate the legacy full-access marker (`"permission": {}`) to the explicit
/// allow-all rule required by current OpenCode. This preserves the user's
/// existing full-access choice instead of silently reverting to approval mode.
pub fn seed_default_permission(existing: &str) -> Option<String> {
    match permission_mode_of(existing) {
        Some(MODE_FULL) => {
            let root: Value = serde_json::from_str(existing).ok()?;
            if root
                .get("permission")
                .is_some_and(|value| value.as_object().is_some_and(|rules| rules.is_empty()))
            {
                return set_permission_mode(existing, MODE_FULL).ok();
            }
            None
        }
        Some(_) => None,
        None => set_permission_mode(existing, MODE_APPROVE).ok(),
    }
}

/// Point OpenCode at the deployed goal plugin while preserving user plugins.
/// Stale AI4HEOR goal-plugin paths are replaced after an application upgrade.
pub fn ensure_goal_plugin(existing: &str, plugin_path: &str) -> Option<String> {
    let mut root: Value = if existing.trim().is_empty() {
        json!({})
    } else {
        serde_json::from_str(existing).ok()?
    };
    if !root.is_object() {
        root = json!({});
    }
    let plugins = root
        .as_object_mut()?
        .entry("plugin")
        .or_insert_with(|| json!([]));
    if !plugins.is_array() {
        *plugins = json!([]);
    }
    let entries = plugins.as_array_mut()?;
    let ours = |value: &Value| {
        value
            .as_str()
            .is_some_and(|path| path.ends_with("goal-plugin.server.js"))
    };
    if entries
        .iter()
        .any(|value| value.as_str() == Some(plugin_path))
        && entries.iter().filter(|value| ours(value)).count() == 1
    {
        return None;
    }
    entries.retain(|value| !ours(value));
    entries.push(json!(plugin_path));
    serde_json::to_string_pretty(&root).ok()
}

/// The approval mode a config encodes: None when the `permission` key was
/// never written (first run — the caller seeds the "approve" default).
pub fn permission_mode_of(existing: &str) -> Option<&'static str> {
    let root: Value = serde_json::from_str(existing).ok()?;
    let permission = root.get("permission")?;
    if permission.get("bash").is_some_and(|b| b.is_object()) {
        Some(MODE_APPROVE)
    } else {
        Some(MODE_FULL)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::Path;

    #[test]
    fn product_harness_config_preserves_existing_config_and_loads_harness_last() {
        let harness = Path::new("/Applications/AI4HEOR.app/Contents/Resources/harness/AGENTS.md");
        let existing = r#"{"instructions":["PROJECT.md","https://example.test/rules"],"model":"provider/model"}"#;

        let out = product_harness_config_content(Some(existing), harness).unwrap();
        let value: Value = serde_json::from_str(&out).unwrap();
        assert_eq!(value["model"], "provider/model");
        assert_eq!(
            value["instructions"],
            json!([
                "PROJECT.md",
                "https://example.test/rules",
                "/Applications/AI4HEOR.app/Contents/Resources/harness/AGENTS.md"
            ])
        );

        let repeated = product_harness_config_content(Some(&out), harness).unwrap();
        assert_eq!(
            serde_json::from_str::<Value>(&repeated).unwrap(),
            value,
            "runtime restarts must not duplicate the product Harness"
        );
    }

    #[test]
    fn product_harness_config_creates_an_ephemeral_config_when_none_is_inherited() {
        let harness = Path::new("/Applications/AI4HEOR.app/Contents/Resources/harness/AGENTS.md");
        for existing in [None, Some(""), Some("   ")] {
            let out = product_harness_config_content(existing, harness).unwrap();
            let value: Value = serde_json::from_str(&out).unwrap();
            assert_eq!(
                value,
                json!({
                    "instructions": [
                        "/Applications/AI4HEOR.app/Contents/Resources/harness/AGENTS.md"
                    ]
                })
            );
        }
    }

    #[test]
    fn product_harness_config_rejects_invalid_inherited_contracts() {
        let harness = Path::new("/Applications/AI4HEOR.app/Contents/Resources/harness/AGENTS.md");
        for existing in [
            "{broken",
            "[]",
            r#"{"instructions":"PROJECT.md"}"#,
            r#"{"instructions":["PROJECT.md",7]}"#,
        ] {
            assert!(product_harness_config_content(Some(existing), harness).is_err());
        }
        assert!(product_harness_config_content(None, Path::new("harness/AGENTS.md")).is_err());
    }

    #[test]
    fn approve_mode_writes_ask_rules_for_dangerous_bash() {
        let out = set_permission_mode("", MODE_APPROVE).unwrap();
        let v: Value = serde_json::from_str(&out).unwrap();
        let bash = v["permission"]["bash"].as_object().unwrap();
        // Prefix form gates a command that starts with the token (also bare,
        // via OpenCode's trailing-" *" optionalization)…
        assert_eq!(bash["rm *"], "ask");
        assert_eq!(bash["pip install *"], "ask");
        assert_eq!(bash["git push *"], "ask");
        // …and the embedded form catches it inside a compound command
        // ("cd x && rm -rf y").
        assert_eq!(bash["* rm *"], "ask");
        assert_eq!(bash["* ssh *"], "ask");
        // No blanket rule of our own: everything else falls through to the
        // builtin "*": "allow" (rules are last-match-wins, ours come last).
        assert!(!bash.contains_key("*"));
        assert_eq!(v["permission"]["webfetch"], "ask");
    }

    #[test]
    fn full_mode_writes_explicit_allow_all_rule() {
        let approved = set_permission_mode("", MODE_APPROVE).unwrap();
        let out = set_permission_mode(&approved, MODE_FULL).unwrap();
        let v: Value = serde_json::from_str(&out).unwrap();
        // Explicitly override builtin asks (notably external_directory) so a
        // full-access or automated test task never waits for confirmation.
        assert_eq!(v["permission"], json!({ "*": "allow" }));
    }

    #[test]
    fn set_permission_mode_preserves_unrelated_keys() {
        let existing =
            r#"{"model":"anthropic/claude","provider":{"openai":{"options":{"apiKey":"k"}}}}"#;
        let out = set_permission_mode(existing, MODE_APPROVE).unwrap();
        let v: Value = serde_json::from_str(&out).unwrap();
        assert_eq!(v["model"], "anthropic/claude");
        assert_eq!(v["provider"]["openai"]["options"]["apiKey"], "k");
    }

    #[test]
    fn set_permission_mode_rejects_unknown_mode() {
        assert!(set_permission_mode("", "off").is_err());
    }

    #[test]
    fn seeds_approve_default_only_when_never_configured() {
        // First run: no permission key → seed the safe default.
        let seeded = seed_default_permission("").unwrap();
        let v: Value = serde_json::from_str(&seeded).unwrap();
        assert_eq!(v["permission"]["bash"]["rm *"], "ask");
        // Explicit user choice (either mode) is never overridden.
        assert!(seed_default_permission(&seeded).is_none());
        let full = set_permission_mode(&seeded, MODE_FULL).unwrap();
        assert!(seed_default_permission(&full).is_none());
        // Versions before 1.0.0 used an empty object for full access. Keep the
        // user's choice while upgrading it to the effective allow-all rule.
        let migrated = seed_default_permission(r#"{"model":"m","permission":{}}"#).unwrap();
        let migrated_value: Value = serde_json::from_str(&migrated).unwrap();
        assert_eq!(migrated_value["permission"], json!({ "*": "allow" }));
        assert_eq!(migrated_value["model"], "m");
        // Other keys survive seeding.
        let seeded2 = seed_default_permission(r#"{"model":"m"}"#).unwrap();
        let v2: Value = serde_json::from_str(&seeded2).unwrap();
        assert_eq!(v2["model"], "m");
    }

    #[test]
    fn permission_mode_of_detects_each_state() {
        // Never configured (first run) — the caller must seed the default.
        assert_eq!(permission_mode_of(""), None);
        assert_eq!(permission_mode_of(r#"{"model":"m"}"#), None);
        let approved = set_permission_mode("", MODE_APPROVE).unwrap();
        assert_eq!(permission_mode_of(&approved), Some(MODE_APPROVE));
        let full = set_permission_mode(&approved, MODE_FULL).unwrap();
        assert_eq!(permission_mode_of(&full), Some(MODE_FULL));
    }
}
