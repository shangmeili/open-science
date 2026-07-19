# Connect evidence, computation, and optional MCP tools

AI4HEOR has three deliberately different capability tiers. A tool can help the
researcher carry out work; it does not acquire scientific judgment, method
selection, approval, or reimbursement authority.

## 1. Built-in governed HEOR evidence

`$heor-evidence-search` is a first-party capability for PubMed and
ClinicalTrials.gov metadata. It uses fixed HTTPS endpoints, an exact
request hash, a declared non-sensitive egress shape, explicit Human network
authorization, immutable response hashes, and candidate-only import. Search
results never become included or appraised evidence automatically.

This is a native AI4HEOR route, not an arbitrary MCP passthrough.

## 2. Managed local computation

Settings → **Evidence and MCP tools** offers Jupyter as a one-click local
computation environment. The app provisions it with bundled `uv`, registers the
local server, and keeps notebook execution under the existing command approval
and provenance flow. Jupyter is an execution surface, not HEOR method authority.

## 3. Researcher-managed MCP servers

Any MCP server works — internal ELN, LIMS, a database gateway, an instrument
bridge, or a separately reviewed research tool. In Settings → **Evidence and
MCP tools**, use the add form:

- **local** — a command the app launches and talks to over stdio. Example:
  `npx -y @playwright/mcp` (browser), or `uvx your-lab-mcp` for a Python server.
- **remote** — a URL the app connects to over HTTP. Example:
  `https://mcp.your-lab.internal/sse`.

The entry is written to the bundled OpenCode configuration and applies
immediately; its live status (connected / failed) shows in the same list.
User-added servers are unmanaged external capabilities: the researcher must
review their code, license, data egress, credentials, and source-specific rights.
Adding one does not admit it as an AI4HEOR product asset.

## Why there is no generic one-click connector catalog

The inherited Open Science catalog has been retired from the AI4HEOR default
surface. Existing configured servers remain visible, runnable, and removable so
upgrades do not destroy researcher configuration; new installations do not
re-offer those entries.

- [Paper Search MCP](https://github.com/openags/paper-search-mcp) was removed
  from the product list. Its useful official-source metadata pattern is handled
  by the bounded, Human-authorized first-party evidence route; its broad
  multi-host download and optional Sci-Hub surfaces are not retained.
- [BioMCP](https://github.com/genomoncology/biomcp) was removed from the product
  list. Trial and literature needs are handled by first-party HEOR evidence
  capabilities; any future source-specific need must be implemented and reviewed
  independently rather than reactivating the broad upstream package.

Neither package is bundled, provisioned, or offered as an AI4HEOR candidate.

### Minimal local MCP server (Python)

```python
# lab_tools.py — run with: uvx --from fastmcp fastmcp run lab_tools.py
from fastmcp import FastMCP

mcp = FastMCP("lab-tools")

@mcp.tool()
def sample_metadata(sample_id: str) -> dict:
    """Look up a sample in the lab database."""
    return {"id": sample_id, "assay": "RNA-seq", "status": "passed_qc"}

if __name__ == "__main__":
    mcp.run()
```

Add it as a **local** server with the command that launches it. Restart-free.

## Bring your own skill

A skill is a folder with a `SKILL.md` (instructions the agent follows) plus any
scripts/templates it needs. The **Skills** page evaluates an external candidate
through natural-language review but does not install or enable it. Advanced
users may place their own content under the workspace's `.opencode/skills/`;
the app labels that content unmanaged, and it never becomes a bundled product
asset automatically. AI4HEOR bundles only first-party skills plus any future
third-party adapter that passes the packaged, hash-locked admission registry.

## Safety

- Every server or workspace Skill you add can make its own network calls and run
  its own code. Review it before enabling; user-added entries are outside the
  bundled asset admission boundary.
- Command execution, file deletion, dependency installs, and remote connections
  still go through the agent's approval flow.
- Provider keys and tokens live in an app-private file, never in the workspace,
  provenance, logs, or exports.
