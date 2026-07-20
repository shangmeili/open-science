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
Dieser Benchmark der Upstream-Plattform belegt weder, dass Forschung in AI4HEOR von einem Agenten geleitet werden soll, noch die Gültigkeit ihrer Ergebnisse.

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

**Unterstützt einen vom Menschen geleiteten HEOR-Workflow** — von der forschungsseitig definierten Frage über prüfbare Evidenz und deterministische Analysen bis zu Validierungs- und Berichtsartefakten in einer auditierbaren Sitzung.

- **Natural-Language-First-Unterstützung**: Forschende starten und steuern die Arbeit; Modell/Runtime schlagen begrenzte Schritte vor oder führen sie aus, ohne wissenschaftliche Autorität zu übernehmen.
- **Alles ist rückverfolgbar**: Abbildungen, Tabellen, Berichte, Notebooks und Lauf-Ausgaben verweisen auf den exakten Code, die Inputs, die Umgebung, die Modellausgabe und das Gespräch, die sie erzeugt haben.
- **Local-first und deins**: Sitzungen, Daten, Provenance, Notebooks und Run Records liegen in lokalen Ordnern auf deinem Gerät. Standardmäßig verlässt nichts das Gerät.
- **Modellunabhängige Laufzeit**: Die UI spricht über `packages/sdk` mit einem gebündelten, gepinnten OpenCode-Sidecar. Bring dein eigenes Modell mit; Provider, Skills und MCP-Server bleiben austauschbar.
- **Reproduzierbar von Grund auf**: Lokale, SSH/Slurm-, Modal- und Notebook-Batch-Läufe werden als reproduzierbare Run Records erfasst, nicht als loser Terminal-Output.
- **Kontrolliert erweiterbar**: First-Party-HEOR-Skills, von Forschenden verwaltete MCP-Server, `/`-Befehle, `!`-Shell-Modus und ein modellunabhängiges SDK.

## Screenshots

![Erstnutzung mit Grenzen für lokale Daten, Modellwahl, Freigaben und Human-Autorität](./docs/audits/2026-07-17-first-use/06-skip-link-stable.png)

![HEOR-spezifischer Einstieg über natürliche Sprache](./docs/audits/2026-07-17-first-use/07-heor-workspace-final.png)

![Bearbeitbare Kosten-Effektivitäts-Anfrage vor einem Modellaufruf](./docs/audits/2026-07-17-first-use/08-natural-language-draft-final.png)

## Aktuelle Funktionen

**HEOR-Unterstützung als begrenzte Skills.** Die 52 First-Party-Skills routen Aufgaben, die Forschende definiert haben, ohne Freigabe- oder Methodenwahl-Autorität zu übernehmen. Repräsentative Workflows:

| Skill | Rolle | Hauptausgabe |
| --- | --- | --- |
| `$heor-workbench` | Vom Menschen geleitete HEOR-Arbeit koordinieren | Prüfbarer lokaler Plan, Artefakte und Stopppunkte |
| `$heor-local-evidence` | Gewählte lokale Wissensbasis ohne automatischen Netzzugriff inventarisieren | Hash-gebundenes lokales Evidenzinventar |
| `$heor-evidence-search` | Human-autorisierte PubMed/ClinicalTrials.gov-Suche vorbereiten | Exakter Request-Hash und Metadatenkandidaten |
| `$literature-review` | Projektinterne Literaturdaten importieren, deduplizieren, validieren und exportieren | Quellengebundene Literaturbibliothek plus RIS-, BibTeX- oder CSL-JSON-Austauschdatei |
| `$heor-model-design` | Menschlich definiertes Entscheidungsproblem und konzeptionelles Modell strukturieren | Entscheidungs- und Modellartefakte |
| `$heor-cohort-state-transition` / `$heor-partitioned-survival` | Begrenzte deterministische ökonomische Modelle ausführen | Reproduzierbare Kosten, QALYs, Inkremente und Prüfungen |
| `$heor-uncertainty-analysis` / `$heor-advanced-value-of-information` | Deklarierte Unsicherheit und begrenzte VOI ausführen | DSA/PSA/CEAC/CEAF/EVPI und separat geprüfte erweiterte VOI |
| `$heor-budget-impact` / `$heor-dynamic-budget-impact` | Statische oder dynamische Budgetwirkung ausführen | Aufgeschlüsselte Budgetergebnisse und Audit-Artefakte |
| `$heor-model-validation` / `$heor-reporting` / `$heor-reproducibility-package` | Exakte aktuelle Artefakte validieren, berichten und paketieren | Unabhängiges Review-Paket, Bericht und Replay-Bundle |
| `$research-presentation` | Quellengebundene Präsentationsinhalte vorbereiten und lokal erzeugen | Prüfbare makrofreie PPTX mit Generierungsnachweis |
| `$research-tables` | Typisierte, einheiten- und quellengebundene Forschungstabellen vorbereiten | Prüfbare formelfreie XLSX, CSV je Tabelle und Generierungsnachweis |
| `$journal-submission-check` | Explizite formale Vorgaben aus einer von Forschenden gespeicherten offiziellen Autorenrichtlinie erfassen | Quellengebundener Prüfbericht, der auf die menschliche Prüfung wartet |

Namen und Beschreibungen aller 52 First-Party-Skills werden in sieben UI-Sprachen ausgeliefert; die exakte `$skill-id` bleibt sichtbar. Externe Assets bleiben bis zur Einzelzulassung inaktiv.

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

Die Standardoberfläche startet keine ungeprüften Third-Party-MCPs. `$heor-evidence-search` greift nur nach ausdrücklicher Human-Freigabe auf feste PubMed- und ClinicalTrials.gov-Metadatenendpunkte zu; Jupyter ist das einzige verwaltete lokale Ein-Klick-Werkzeug. In Settings ergänzte MCPs werden als nicht verwaltete externe Fähigkeiten markiert und erhalten keine wissenschaftliche oder Freigabeautorität. Siehe [`docs/CONNECT_YOUR_TOOLS.md`](./docs/CONNECT_YOUR_TOOLS.md).

## Installation

Lade den neuesten Installer von [Releases](https://github.com/ai4s-research/open-science/releases/latest).

- **macOS**: `.dmg` / `.app`, Apple Silicon und Intel, macOS 13 Ventura oder neuer.
- **Windows**: NSIS `.exe` und `.msi`, Windows 10/11 x64.
- **Linux**: `.deb` und `.rpm` für x86_64.

Die Builds sind noch nicht signiert. Falls macOS die App blockiert:

```bash
xattr -cr "/Applications/AI4HEOR.app"
```

Unter Windows in SmartScreen **More info -> Run anyway** wählen.

## Aus dem Quellcode bauen

```bash
git clone https://github.com/ai4s-research/open-science
cd open-science
pnpm install
bash scripts/dev/fetch-opencode.sh
bash scripts/dev/fetch-uv.sh
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
| `runtime/skills/external/` | Optionaler Review-Cache für externe Kandidaten; standardmäßig nicht gebündelt. |
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
  version = {0.1.52},
  url     = {https://github.com/ai4s-research/open-science},
  license = {MIT}
}
```

GitHubs **„Cite this repository“**-Button (aus [`CITATION.cff`](./CITATION.cff) generiert) liefert dieselbe Referenz als APA und BibTeX.
