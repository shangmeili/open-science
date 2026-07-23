<div align="center">

[![Open Science Desktop — Local-first AI research workbench](./docs/assets/banner.webp)](https://github.com/ai4s-research/open-science)

# Open Science Desktop

**Atelier de recherche IA local-first et agnostique au modèle pour macOS, Windows & Linux.**

Formerly Open Science. Une alternative desktop open source à Claude Science et aux workbenches AI-for-science similaires, construite avec Tauri, MCP, agent skills et des artefacts reproductibles. Elle relie agents, notebooks, fichiers, figures, rapports, exécutions et revue dans un flux desktop auditable.

<p>
  <a href="./README.md">English</a> ·
  <a href="./README.zh.md">简体中文</a> ·
  <a href="./README.ja.md">日本語</a> ·
  <a href="./README.es.md">Español</a> ·
  <a href="./README.de.md">Deutsch</a> ·
  <b>Français</b> ·
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

🎉 **Reconnaissance :** Open Science Desktop est n° 1 au score moyen des tâches évaluées sur [ResearchClawBench](https://internscience.github.io/ResearchClawBench-Home/), un benchmark de bout en bout pour agents autonomes de recherche scientifique (classement Pass@1, 9 juillet 2026).
Ce benchmark de la plateforme amont ne prouve ni que la recherche dans AI4HEOR doit être dirigée par un agent, ni la validité de ses résultats.

---

## Sommaire

- [✨ Ce que fait AI4HEOR](#ce-que-fait-ai4heor)
- [🎬 Captures](#captures)
- [🧪 Fonctionnalités actuelles](#fonctionnalités-actuelles)
- [🔌 Skills et connecteurs](#skills-et-connecteurs)
- [📦 Installation](#installation)
- [🚀 Construire depuis le code source](#construire-depuis-le-code-source)
- [🔒 Sécurité et confidentialité](#sécurité-et-confidentialité)
- [🗂️ Structure du dépôt](#structure-du-dépôt)
- [📌 État](#état)

## Ce que fait AI4HEOR

**Assiste un workflow HEOR dirigé par le chercheur humain** — depuis la question définie par le chercheur jusqu'aux données probantes révisables, analyses déterministes, validations et artefacts de rapport dans une session auditable.

- **Assistance natural-language-first** : le chercheur démarre et contrôle le travail ; le modèle/runtime propose ou exécute des étapes bornées sans acquérir d'autorité scientifique.
- **Tout est traçable** : figures, tables, rapports, notebooks et sorties d'exécution renvoient au code, aux entrées, à l'environnement, à la sortie du modèle et à la conversation exacts qui les ont produits.
- **Local-first et à vous** : sessions, données, provenance, notebooks et run records vivent dans des dossiers locaux sur votre machine. Rien ne sort par défaut.
- **Runtime agnostique au modèle** : l'UI passe par `packages/sdk` vers un sidecar OpenCode épinglé et intégré. Apportez votre propre modèle ; fournisseurs, skills et serveurs MCP restent remplaçables.
- **Reproductible par conception** : les exécutions locales, SSH/Slurm, Modal et notebook-batch sont enregistrées comme run records reproductibles, pas comme sortie de terminal éparse.
- **Extensible sous gouvernance** : skills HEOR internes, serveurs MCP gérés par le chercheur, commandes `/`, mode shell `!` et SDK agnostique au modèle.

## Captures

![Guide initial explicitant stockage local, modèle, autorisations et autorité Human](./docs/audits/2026-07-17-first-use/06-skip-link-stable.png)

![Entrée en langage naturel propre au HEOR](./docs/audits/2026-07-17-first-use/07-heor-workspace-final.png)

![Demande coût-efficacité modifiable avant tout appel au modèle](./docs/audits/2026-07-17-first-use/08-natural-language-draft-final.png)

## Fonctionnalités actuelles

**Socle Open Science complet, renforcé par des skills HEOR bornés.** L'application distribue 52 skills HEOR internes et 7 skills généraux Open Science sous licence MIT et verrouillés par hash. Aucun n'acquiert d'autorité d'approbation ou de choix méthodologique.

| Skill | Rôle | Sortie principale |
| --- | --- | --- |
| `$heor-workbench` | Coordonner un travail HEOR dirigé par le chercheur | Plan local, artefacts et points d'arrêt révisables |
| `$heor-local-evidence` | Inventorier une base locale sélectionnée sans accès réseau automatique | Inventaire local lié par hash |
| `$heor-evidence-search` | Préparer une recherche PubMed/ClinicalTrials.gov soumise à autorisation Human | Hash exact de requête et candidats de métadonnées |
| `$literature-review` | Importer, dédupliquer, valider et exporter les références du projet | Bibliothèque liée aux sources et fichier RIS, BibTeX ou CSL-JSON |
| `$heor-model-design` | Structurer le problème décisionnel et le modèle conceptuel définis par l'humain | Artefacts de décision et de modèle conceptuel |
| `$heor-cohort-state-transition` / `$heor-partitioned-survival` | Exécuter des modèles économiques déterministes bornés | Coûts, QALY, incréments et contrôles reproductibles |
| `$heor-uncertainty-analysis` / `$heor-advanced-value-of-information` | Exécuter l'incertitude déclarée et une VOI bornée | DSA/PSA/CEAC/CEAF/EVPI et VOI avancée revue séparément |
| `$heor-budget-impact` / `$heor-dynamic-budget-impact` | Exécuter une analyse d'impact budgétaire statique ou dynamique | Résultats ventilés et artefacts d'audit |
| `$heor-model-validation` / `$heor-reporting` / `$heor-reproducibility-package` | Valider, rapporter et empaqueter les artefacts courants exacts | Package de revue indépendante, rapport et bundle de rejeu |
| `$research-presentation` | Préparer un contenu lié aux sources et le produire localement | PPTX sans macro vérifiable et audit de génération |
| `$research-tables` | Préparer des tableaux typés avec unités et sources explicites | XLSX sans formule vérifiable, un CSV par tableau et audit de génération |
| `$journal-submission-check` | Consigner les exigences formelles explicites depuis un guide officiel conservé par le chercheur | Rapport lié à la source et en attente de revue humaine |

Les noms et descriptions des 59 skills sont fournis dans les sept langues de l'interface avec le `$skill-id` exact visible.

### Plateforme

| Domaine | État actuel |
| --- | --- |
| Desktop | Tauri 2 + React + TypeScript + Vite, avec cibles macOS, Windows et Linux. |
| Runtime | Sidecar OpenCode inclus, démarré par l'app et isolé de la configuration/données OpenCode de l'utilisateur. |
| Sessions | Chat multi-session, historique, dossiers workspace datés, historique global, commandes `/` et mode shell `!`. |
| Fichiers | Navigation globale et par session, menu contextuel, ouvrir/révéler, copier le chemin, serveur local de preview. |
| Notebooks | Fichiers `.ipynb` réels, création Python/R, kernel local, environnement Jupyter géré via `uv`, action Open JupyterLab. |
| Exécutions | Run logs append-only, index SQLite global, recherche/facettes/pagination, surfaces locales/distantes, liens de sorties, logs et prompts de reproduction. |
| Provenance | `.openscience/provenance.jsonl` enregistre les versions de fichiers et relie les artefacts à l'exécution ou l'édition qui les a créés. |
| Visionneuses | PDF, image, vidéo, HTML, Markdown, code, CSV/TSV avec graphiques, DOCX, XLSX, PPTX, molécules, 3D mesh, génome, FITS, DOS/DOSCAR, EIGENVAL bands, qcode, cartes d'anomalies et fichiers phase. |
| Langues de l'UI | English, 简体中文, 日本語, Español, Deutsch, Français et 한국어. Portuguese (Brazil) et Arabic sont enregistrés mais pas encore sélectionnables. |

## Skills et connecteurs

L'application distribue 52 skills HEOR internes depuis `runtime/skills/core/` ainsi que 7 skills généraux Open Science issus d'un commit fixe, avec licence MIT et hash d'arborescence vérifiés. Les skills documentaires d'Anthropic ne sont pas inclus car leur licence interdit la redistribution.

Les sept connecteurs de recherche Open Science — Paper Search, BioMCP, Materials Project, FRED, Space Weather, Open-Meteo et USGS Water — s'installent à la demande dans un environnement géré par l'application. `$heor-evidence-search` reste le parcours auditable pour les preuves HEOR ; un résultat de connecteur général ne devient pas automatiquement une preuve incluse. Voir [`docs/CONNECT_YOUR_TOOLS.md`](./docs/CONNECT_YOUR_TOOLS.md).

## Installation

Téléchargez la dernière version depuis [Releases](https://github.com/ai4s-research/open-science/releases/latest).

- **macOS** : `.dmg` / `.app`, Apple Silicon et Intel, macOS 13 Ventura ou plus récent.
- **Windows** : `.exe` NSIS et `.msi`, Windows 10/11 x64.
- **Linux** : `.deb` et `.rpm` pour x86_64.

Les builds ne sont pas encore signés. Si macOS bloque l'app :

```bash
xattr -cr "/Applications/AI4HEOR.app"
```

Sous Windows, choisissez **More info -> Run anyway** dans SmartScreen.

## Construire depuis le code source

```bash
git clone https://github.com/ai4s-research/open-science
cd open-science
pnpm install
bash scripts/dev/fetch-opencode.sh
bash scripts/dev/fetch-uv.sh
pnpm --filter @ai4s/desktop tauri dev
pnpm --filter @ai4s/desktop tauri build
```

Vérifications :

```bash
pnpm test
pnpm typecheck
pnpm lint
```

## Sécurité et confidentialité

Les fichiers du workspace, données brutes, historique, provenance, notebooks et run records restent locaux par défaut. Exécution de commandes, suppression de fichiers, installation de dépendances et connexions distantes passent par une approbation humaine. Les identifiants sont stockés dans la configuration privée de l'app, pas dans le workspace, la provenance, git, les exports ni la configuration OpenCode globale.

## Structure du dépôt

| Chemin | Rôle |
| --- | --- |
| `apps/desktop/` | App desktop Tauri + React. |
| `packages/sdk/` | `OpenCodeClient`, couche qui évite les appels directs UI -> OpenCode. |
| `packages/shared/` | Types partagés et palette de graphiques. |
| `runtime/skills/core/` | Skills scientifiques internes. |
| `runtime/skills/external/` | Cache de revue facultatif pour candidats externes ; non inclus par défaut. |
| `examples/` | Workspaces d'exemple inclus. |
| `scripts/dev/` | Fetchers sidecar, `uv`, skills et tests ciblés. |
| `docs/` | Notes produit, technique, operator, connecteurs et recherche. |

## État

Le journal d'implémentation le plus fiable est [`PROGRESS.md`](./PROGRESS.md). Les prochains travaux portent sur les releases signées/notarisées, la vérification Windows/Linux, l'auto-update, le durcissement des connecteurs et la revue de reproductibilité. Pour discuter du projet, rejoignez le [Discord Open Science](https://discord.gg/fWNMDKcd5P).

[MIT](./LICENSE). Open Science Desktop est un outil de recherche beta : traitez les sorties comme des brouillons et vérifiez nombres, citations, code et conclusions avant publication ou décision.

## Citation

Si vous utilisez Open Science Desktop dans vos recherches, merci de le citer ainsi :

```bibtex
@software{open_science_desktop,
  author  = {{The Open Science Desktop Contributors}},
  title   = {Open Science Desktop: a local-first, model-agnostic AI research workbench},
  year    = {2026},
  version = {1.0.0},
  url     = {https://github.com/ai4s-research/open-science},
  license = {MIT}
}
```

Le bouton **« Cite this repository »** de GitHub (généré depuis [`CITATION.cff`](./CITATION.cff)) fournit la même référence en APA et BibTeX.
