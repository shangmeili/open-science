// Pure OpenCode permission configuration used by the runtime command layer.
use serde_json::{json, Value};

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

fn approve_permission() -> Value {
    let mut bash = serde_json::Map::new();
    for t in DANGEROUS_BASH {
        bash.insert(format!("{t} *"), json!("ask"));
        bash.insert(format!("* {t} *"), json!("ask"));
    }
    json!({ "bash": Value::Object(bash), "webfetch": "ask" })
}

/// Set the approval mode in OpenCode config JSON. "approve" installs the ask
/// rules; "full" writes `"permission": {}` — zero rules (builtin defaults),
/// with the key's presence marking that the user made a choice (so startup
/// seeding never overrides it). Other keys are preserved.
pub fn set_permission_mode(existing: &str, mode: &str) -> Result<String, String> {
    let permission = match mode {
        MODE_APPROVE => approve_permission(),
        MODE_FULL => json!({}),
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

/// Seed the "approve" default on first run (no `permission` key yet).
/// Returns None when the user already chose a mode — never overrides it.
pub fn seed_default_permission(existing: &str) -> Option<String> {
    if permission_mode_of(existing).is_some() {
        return None;
    }
    set_permission_mode(existing, MODE_APPROVE).ok()
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
    fn full_mode_writes_empty_permission_marker() {
        let approved = set_permission_mode("", MODE_APPROVE).unwrap();
        let out = set_permission_mode(&approved, MODE_FULL).unwrap();
        let v: Value = serde_json::from_str(&out).unwrap();
        // {} = zero rules = OpenCode builtin defaults; the key's presence
        // marks "user chose this" so startup never re-seeds approve mode.
        assert_eq!(v["permission"], json!({}));
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
