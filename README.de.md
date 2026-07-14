<div align="center">

[![Open Science Desktop — Local-first AI research workbench](./docs/assets/banner.webp)](https://github.com/ai4s-research/open-science)

# Open Science Desktop

**Local-first, modellunabhängige KI-Forschungs-Workbench für macOS, Windows & Linux.**

Formerly Open Science. Eine quelloffene Desktop-Alternative zu Claude Science und ähnlichen AI-for-science-Workbenches, gebaut mit Tauri, MCP, agent skills und reproduzierbaren Artefakten. Agenten, Notebooks, Dateien, Abbildungen, Berichte, Läufe und Reviews werden zu einem auditierbaren Desktop-Workflow verbunden.

<p>
  <a href="./README.md">English</a> ·
  <a href="./README.zh.md">简体中文</a> ·
  <a href="./README.ja.md">日本語</a> ·
  <a href="./README.es.md">Español</a> ·
  <b>Deutsch</b> ·
  <a href="./README.fr.md">Français</a> ·
  <a href="./README.ko.md">한국어</a>
</p>

<p>
  <a href="./LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="License: MIT"></a>
  <a href="https://internscience.github.io/ResearchClawBench-Home/"><img src="https://img.shields.io/badge/%F0%9F%8F%86%20%231-ResearchClawBench-FFB300" alt="#1 on ResearchClawBench"></a>
  <img src="https://img.shields.io/badge/platform-macOS%20%7C%20Windows%20%7C%20Linux-blue" alt="Platforms">
  <img src="https://img.shields.io/badge/i18n-7%20languages-5B8DEF" alt="7 interface languages">
  <img src="https://img.shields.io/badge/built%20with-Tauri%202%20%2B%20React-24C8DB" alt="Built with Tauri + React">
  <img src="https://img.shields.io/badge/runtime-OpenCode-success" alt="OpenCode runtime">
  <a href="https://discord.gg/fWNMDKcd5P"><img src="https://img.shields.io/badge/Join-Discord-5865F2" alt="Join Discord"></a>
</p>

</div>

---

🎉 **Anerkennung:** Open Science Desktop belegt nach Durchschnitt der bewerteten Aufgaben Platz 1 auf [ResearchClawBench](https://internscience.github.io/ResearchClawBench-Home/), einem End-to-End-Benchmark für autonome wissenschaftliche Forschungsagenten (Pass@1-Leaderboard, 9. Juli 2026).

---

## Inhalt

- [✨ Was es leistet](#was-es-leistet)
- [🎬 Screenshots](#screenshots)
- [🧪 Aktuelle Funktionen](#aktuelle-funktionen)
- [🔌 Skills und Konnektoren](#skills-und-konnektoren)
- [📦 Installation](#installation)
- [🚀 Aus dem Quellcode bauen](#aus-dem-quellcode-bauen)
- [🔒 Sicherheit und Datenschutz](#sicherheit-und-datenschutz)
- [🗂️ Repository-Struktur](#repository-struktur)
- [📌 Status](#status)

## Was es leistet

**Durchläuft die gesamte Forschungsschleife** — von einer groben Richtung bis zum fertigen Paper: Exploration, Literaturüberblick, Hypothese, Experiment-Code, Analyse, Abbildungen und Ausarbeitung, in einer durchgängigen, auditierbaren Sitzung.

- **Autonome Forschungs-Agenten**: Der gebündelte `ai4s-agent` verkettet Spezial-Skills Ende zu Ende (Explore → Survey → Experiment → Write), und jeder Schritt legt ein echtes, prüfbares Artefakt in deinen Workspace, nicht nur eine Chat-Antwort.
- **Alles ist rückverfolgbar**: Abbildungen, Tabellen, Berichte, Notebooks und Lauf-Ausgaben verweisen auf den exakten Code, die Inputs, die Umgebung, die Modellausgabe und das Gespräch, die sie erzeugt haben.
- **Local-first und deins**: Sitzungen, Daten, Provenance, Notebooks und Run Records liegen in lokalen Ordnern auf deinem Gerät. Standardmäßig verlässt nichts das Gerät.
- **Modellunabhängige Laufzeit**: Die UI spricht über `packages/sdk` mit einem gebündelten, gepinnten OpenCode-Sidecar. Bring dein eigenes Modell mit; Provider, Skills und MCP-Server bleiben austauschbar.
- **Reproduzierbar von Grund auf**: Lokale, SSH/Slurm-, Modal- und Notebook-Batch-Läufe werden als reproduzierbare Run Records erfasst, nicht als loser Terminal-Output.
- **Erweiterbar**: Agent-Skills, MCP-Server und Ein-Klick-Wissenschaftskonnektoren, `/`-Befehle, `!`-Shell-Modus und ein modellunabhängiges SDK.

## Screenshots

![End-to-end dose-response analysis](./docs/assets/showcase-workflow.webp)

![Artifact inspector showing provenance](./docs/assets/showcase-provenance.webp)

![Literature survey producing a rendered PDF manuscript](./docs/assets/showcase-literature.webp)

<details>
<summary><b>Weitere Screenshots</b></summary>

<br>

![Jupyter notebook](./docs/assets/showcase-notebook.webp)

![Experiment sweep](./docs/assets/showcase-experiment.webp)

![Skills library](./docs/assets/showcase-skills.webp)

</details>

## Aktuelle Funktionen

**Die Forschungsschleife als Skills.** Ein Meta-Skill durchläuft die gesamte Pipeline; jede Stufe ist ein eigenständiger Skill, der ein echtes, bewertbares Artefakt erzeugt — lauffähig auf jedem von OpenCode unterstützten Modell:

| Skill | Rolle | Hauptausgabe |
| --- | --- | --- |
| `ai4s-agent` | Führt die vier Skills unten der Reihe nach aus | Das komplette Forschungspaket |
| `research-explorer` | Eine grobe Richtung zu konkreten Themen verdichten | `research_exploration.md`, `topic_matrix.md`, `literature_pre_survey.md` |
| `literature-survey` | Einen Literaturüberblick schreiben | 6–20 S. PDF, 60+ echte Zitate, LaTeX-Quelle, Taxonomie-Abbildungen |
| `experiment-suite` | Ein Experiment-Paket bauen | Design-Dokument, lauffähiger Code, `results.json` mit Provenance, Abbildungen, Bericht |
| `paper-writer` | Ein Forschungspaper schreiben | 8–14 S. PDF, 200+ Zitate, 4–8 Abbildungen, Tabellen |
| `mindmap-render` | Eine Mindmap rendern | Aus einer `topic_matrix.md` generiertes Bild |
| `integrity-auditor` | Die Integrität eines Papers prüfen | Bild-/numerische/logische Befunde, 4-stufige Evidenzbewertung, `audit_report.md` |

Diese `ai4s-skills`-Muster sind als inaktive Anpassungskandidaten registriert und werden nicht als Runtime-Fähigkeiten ausgeliefert. First-Party-Skills von AI4HEOR implementieren den zugelassenen Ablauf.

### Plattform

| Bereich | Aktueller Stand |
| --- | --- |
| Desktop | Tauri 2 + React + TypeScript + Vite, mit Build-Zielen für macOS, Windows und Linux. |
| Runtime | Gebündeltes OpenCode-Sidecar, von der App gestartet und von der OpenCode-Konfiguration des Nutzers isoliert. |
| Sitzungen | Multi-Session-Chat, Verlauf, datierte Workspace-Ordner, globaler Verlauf, `/`-Befehle und `!`-Shell-Modus. |
| Dateien | Globale und sitzungsbezogene Dateiansicht, Kontextmenü, extern öffnen/anzeigen, Pfad kopieren, lokaler Preview-Server. |
| Notebooks | Echte `.ipynb`-Dateien, Python/R-Notebook-Erstellung, lokaler Kernel, Jupyter-Umgebung über gebündeltes `uv`, JupyterLab öffnen. |
| Läufe | Append-only Run Logs, globaler SQLite-Index, Suche/Facetten/Paginierung, lokale und entfernte Oberflächen, Output-Links, Logs und Reproduce-Prompts. |
| Provenance | `.openscience/provenance.jsonl` zeichnet Dateiversionen auf und verbindet Artefakte mit dem erzeugenden Lauf oder Edit. |
| Viewer | PDF, Bild, Video, HTML, Markdown, Code, CSV/TSV mit Charts, DOCX, XLSX, PPTX, Moleküle, 3D Mesh, Genom, FITS, DOS/DOSCAR, EIGENVAL bands, qcode, Anomaly Maps und Phase-Dateien. |
| UI-Sprachen | English, 简体中文, 日本語, Español, Deutsch, Français und 한국어. Portuguese (Brazil) und Arabic sind registriert, aber noch nicht auswählbar. |

## Skills und Konnektoren

Standardmäßig werden nur First-Party-Skills aus `runtime/skills/core/` ausgeliefert. Drittanbieter-Assets bleiben bis zu Lizenz-, Grenz-, Test-, Review-, Plattform- und Hash-Nachweisen inaktiv. Anthropics Dokument-Skills sind wegen ihres Weitergabeverbots abgelehnt.

Ein-Klick-MCP-Konnektoren: Literatursuche, biomedizinische Datenbanken, Materials Project, FRED, Space weather, Open-Meteo und USGS water data. Beliebige lokale oder entfernte MCP-Server können in Settings ergänzt werden.

## Installation

Lade den neuesten Installer von [Releases](https://github.com/ai4s-research/open-science/releases/latest).

- **macOS**: `.dmg` / `.app`, Apple Silicon und Intel, macOS 13 Ventura oder neuer.
- **Windows**: NSIS `.exe` und `.msi`, Windows 10/11 x64.
- **Linux**: `.deb` und `.rpm` für x86_64.

Die Builds sind noch nicht signiert. Falls macOS die App blockiert:

```bash
xattr -cr "/Applications/Open Science.app"
```

Unter Windows in SmartScreen **More info -> Run anyway** wählen.

## Aus dem Quellcode bauen

```bash
git clone https://github.com/ai4s-research/open-science
cd open-science
pnpm install
bash scripts/dev/fetch-opencode.sh
bash scripts/dev/fetch-uv.sh
bash scripts/dev/fetch-skills.sh
pnpm --filter @ai4s/desktop tauri dev
pnpm --filter @ai4s/desktop tauri build
```

Checks:

```bash
pnpm test
pnpm typecheck
pnpm lint
```

## Sicherheit und Datenschutz

Workspace-Dateien, Rohdaten, Sitzungsverlauf, Provenance, Notebooks und Run Records bleiben standardmäßig lokal. Befehlsausführung, Dateilöschung, Dependency-Installation und Remote-Verbindungen laufen über menschliche Genehmigung. Zugangsdaten werden in app-privater Runtime-Konfiguration gespeichert, nicht im Workspace, in Provenance, git, Exporten oder globaler OpenCode-Konfiguration.

## Repository-Struktur

| Pfad | Zweck |
| --- | --- |
| `apps/desktop/` | Tauri + React Desktop-App. |
| `packages/sdk/` | `OpenCodeClient`, damit die UI OpenCode nicht direkt aufruft. |
| `packages/shared/` | Gemeinsame Typen und Chart-Palette. |
| `runtime/skills/core/` | First-Party-Wissenschafts-Skills. |
| `runtime/skills/external/` | Beim Build geholte externe Skills. |
| `examples/` | Mitgelieferte Beispiel-Workspaces. |
| `scripts/dev/` | Fetcher für Sidecar, `uv`, Skills und fokussierte Regressionstests. |
| `docs/` | Produkt-, Technik-, Operator-, Konnektor- und Forschungsnotizen. |

## Status

Das verlässlichste Implementierungslog ist [`PROGRESS.md`](./PROGRESS.md). Nahe Arbeiten: signierte/notarisierte Releases, breitere Windows/Linux-Verifikation, Auto-Update, robustere Konnektoren und weitere Reproduzierbarkeits-Reviews. Für Diskussionen gibt es den [Open Science Discord](https://discord.gg/fWNMDKcd5P).

[MIT](./LICENSE). Open Science Desktop ist Beta-Forschungstooling. Ausgaben sind Entwürfe: Zahlen, Zitate, Code und Schlussfolgerungen vor Veröffentlichung oder Entscheidung prüfen.

## Zitation

Wenn Sie Open Science Desktop in Ihrer Forschung verwenden, zitieren Sie es bitte wie folgt:

```bibtex
@software{open_science_desktop,
  author  = {{The Open Science Desktop Contributors}},
  title   = {Open Science Desktop: a local-first, model-agnostic AI research workbench},
  year    = {2026},
  version = {0.1.9},
  url     = {https://github.com/ai4s-research/open-science},
  license = {MIT}
}
```

GitHubs **„Cite this repository“**-Button (aus [`CITATION.cff`](./CITATION.cff) generiert) liefert dieselbe Referenz als APA und BibTeX.
