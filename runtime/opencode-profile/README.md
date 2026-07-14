# runtime/opencode-profile

The AI4S Workbench **OpenCode profile** — the config + skills the app ships and applies
to the bundled OpenCode runtime (not a user's global OpenCode).

The desktop app runs OpenCode with an app-private config/data dir (isolated via
`XDG_CONFIG_HOME`/`XDG_DATA_HOME`), so nothing here touches `~/.config/opencode`.

## Contents (planned)

```text
opencode.json      # base config applied to the bundled runtime (providers, defaults)
skills/            # AI4S scientific skills (Markdown, agentskills.io format)
agents/            # optional custom agents
```

## How it maps at runtime

- The user's provider key (from Settings) is merged into the app-private `opencode.json`
  by the `configure_opencode` Rust command; the sidecar is restarted to pick it up.
- Skills are NOT shipped from here. First-party skills live under
  `runtime/skills/core/`. Third-party source under `runtime/skills/external/` is
  an inactive review cache; `runtime.rs` may copy only a hash-locked
  `validated-adapter` named by the packaged admission registry into
  `<xdg-config>/opencode/skills/`. The Skills page lists the real runtime state.

Keep this bundle versioned with the app; it must not carry the user's own keys or sessions.
