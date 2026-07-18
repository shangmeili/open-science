<div align="center">

[![Open Science Desktop — Local-first AI research workbench](./docs/assets/banner.webp)](https://github.com/ai4s-research/open-science)

# Open Science Desktop

**Banco de trabajo de investigación con IA, local-first y agnóstico al modelo, para macOS, Windows & Linux.**

Formerly Open Science. Una alternativa desktop open source a Claude Science y workbenches AI-for-science similares, construida con Tauri, MCP, agent skills y artefactos reproducibles. Conecta agentes, notebooks, archivos, figuras, informes, ejecuciones y revisión en un flujo de escritorio auditable.

<p>
  <a href="./README.md">English</a> ·
  <a href="./README.zh.md">简体中文</a> ·
  <a href="./README.ja.md">日本語</a> ·
  <b>Español</b> ·
  <a href="./README.de.md">Deutsch</a> ·
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

🎉 **Reconocimiento:** Open Science Desktop ocupa el puesto #1 por promedio de tareas puntuadas en [ResearchClawBench](https://internscience.github.io/ResearchClawBench-Home/), un benchmark end-to-end para agentes autónomos de investigación científica (leaderboard Pass@1, 9 de julio de 2026).
Este benchmark del proyecto base no demuestra que la ciencia dentro de AI4HEOR deba estar dirigida por un agente ni que sus resultados sean válidos.

---

## Índice

- [✨ Qué hace](#qué-hace)
- [🎬 Capturas](#capturas)
- [🧪 Capacidades actuales](#capacidades-actuales)
- [🔌 Skills y conectores](#skills-y-conectores)
- [📦 Instalación](#instalación)
- [🚀 Compilar desde el código](#compilar-desde-el-código)
- [🔒 Seguridad y privacidad](#seguridad-y-privacidad)
- [🗂️ Estructura del repositorio](#estructura-del-repositorio)
- [📌 Estado](#estado)

## Qué hace

**Apoya un flujo HEOR dirigido por la persona investigadora**: desde una pregunta definida por ella hasta evidencia revisable, análisis determinista, validación y artefactos de informe en una sesión auditable.

- **Asistencia natural-language-first**: la persona investigadora inicia y controla el trabajo; el modelo/runtime propone o ejecuta pasos acotados sin adquirir autoridad científica.
- **Todo es trazable**: figuras, tablas, informes, notebooks y salidas de ejecución enlazan con el código, las entradas, el entorno, la salida del modelo y la conversación exactos que los produjeron.
- **Local-first y tuyo**: sesiones, datos, procedencia, notebooks y registros de ejecución viven en carpetas locales de tu máquina. Nada sale por defecto.
- **Runtime agnóstico al modelo**: la UI habla mediante `packages/sdk` con un sidecar OpenCode fijado y empaquetado. Trae tu propio modelo; proveedores, skills y servidores MCP siguen siendo intercambiables.
- **Reproducible por diseño**: las ejecuciones locales, SSH/Slurm, Modal y notebook-batch se registran como run records reproducibles, no como salida suelta de terminal.
- **Extensible con gobierno**: skills HEOR propias, servidores MCP gestionados por la persona investigadora, comandos `/`, modo shell `!` y un SDK agnóstico al modelo.

## Capturas

![Guía inicial con límites de almacenamiento, modelo, autorización y autoridad humana](./docs/audits/2026-07-17-first-use/06-skip-link-stable.png)

![Entrada HEOR específica basada en lenguaje natural](./docs/audits/2026-07-17-first-use/07-heor-workspace-final.png)

![Solicitud editable de coste-efectividad antes de ejecutar el modelo](./docs/audits/2026-07-17-first-use/08-natural-language-draft-final.png)

## Capacidades actuales

**Asistencia HEOR mediante skills acotadas.** Las 45 skills propias enrutan tareas definidas por la persona investigadora sin adquirir autoridad de aprobación o selección metodológica. Flujos representativos:

| Skill | Rol | Salida principal |
| --- | --- | --- |
| `$heor-workbench` | Coordinar trabajo HEOR dirigido por la persona investigadora | Plan, artefactos y puntos de parada revisables |
| `$heor-local-evidence` | Inventariar una base local seleccionada sin acceso automático a red | Inventario local vinculado por hash |
| `$heor-evidence-search` | Preparar búsquedas PubMed/ClinicalTrials.gov sujetas a autorización humana | Hash exacto de solicitud y candidatos de metadatos |
| `$heor-model-design` | Estructurar el problema de decisión y modelo conceptual definidos por la persona | Artefactos de problema y modelo conceptual |
| `$heor-cohort-state-transition` / `$heor-partitioned-survival` | Ejecutar modelos económicos deterministas acotados | Costes, QALY, incrementos y controles reproducibles |
| `$heor-uncertainty-analysis` / `$heor-advanced-value-of-information` | Ejecutar incertidumbre declarada y VOI acotado | DSA/PSA/CEAC/CEAF/EVPI y VOI avanzado revisado aparte |
| `$heor-budget-impact` / `$heor-dynamic-budget-impact` | Ejecutar impacto presupuestario estático o dinámico | Resultados desglosados y artefactos de auditoría |
| `$heor-model-validation` / `$heor-reporting` / `$heor-reproducibility-package` | Validar, informar y empaquetar artefactos actuales exactos | Paquete de revisión independiente, informe y bundle reproducible |

Los nombres y descripciones de las 45 skills propias se publican en los siete idiomas de interfaz manteniendo visible el `$skill-id` exacto. Los activos externos permanecen inactivos hasta su admisión individual.

### Plataforma

| Área | Estado actual |
| --- | --- |
| Escritorio | Tauri 2 + React + TypeScript + Vite, con objetivos de build para macOS, Windows y Linux. |
| Runtime | Sidecar OpenCode incluido, iniciado por la app y aislado de la configuración/datos OpenCode del usuario. |
| Sesiones | Chat multi-sesión, historial, carpetas fechadas, historial global entre workspaces, comandos `/` y modo shell `!`. |
| Archivos | Navegación global y por sesión, menú contextual, abrir/revelar en el sistema, copiar ruta y servidor local de previsualización. |
| Notebooks | Archivos `.ipynb` reales, creación Python/R, kernel local, entorno Jupyter gestionado con `uv` incluido y acción para abrir JupyterLab. |
| Ejecuciones | Logs append-only, índice SQLite global, búsqueda/facetas/paginación, superficies locales/remotas, enlaces a salidas, logs y prompts de reproducción. |
| Procedencia | `.openscience/provenance.jsonl` registra versiones de archivos y conecta artefactos con la ejecución o edición que los creó. |
| Visores | PDF, imagen, vídeo, HTML, Markdown, código, CSV/TSV con gráficos, DOCX, XLSX, PPTX, moléculas, 3D mesh, genoma, FITS, DOS/DOSCAR, EIGENVAL bands, qcode, mapas de anomalías y phase. |
| Idiomas de UI | English, 简体中文, 日本語, Español, Deutsch, Français y 한국어. Portuguese (Brazil) y Arabic están registrados, pero aún no son seleccionables. |

## Skills y conectores

Por defecto solo se distribuyen las skills propias de `runtime/skills/core/`. Los activos externos permanecen inactivos hasta superar licencia, límites, pruebas, revisiones, evidencia multiplataforma y hash exacto. Las skills documentales de Anthropic se rechazan porque su licencia prohíbe redistribuirlas.

La superficie predeterminada no inicia MCP de terceros sin revisar. `$heor-evidence-search` accede únicamente a metadatos de PubMed y ClinicalTrials.gov tras autorización humana explícita; Jupyter es la única herramienta local gestionada de un clic. Los MCP añadidos en Settings se etiquetan como capacidades externas no gestionadas y no reciben autoridad científica ni de aprobación. Consulta [`docs/CONNECT_YOUR_TOOLS.md`](./docs/CONNECT_YOUR_TOOLS.md).

## Instalación

Descarga la versión más reciente desde [Releases](https://github.com/ai4s-research/open-science/releases/latest).

- **macOS**: `.dmg` / `.app`, Apple Silicon e Intel, macOS 13 Ventura o posterior.
- **Windows**: `.exe` NSIS y `.msi`, Windows 10/11 x64.
- **Linux**: `.deb` y `.rpm` para x86_64.

Los builds aún no están firmados. En macOS, si Gatekeeper bloquea la app:

```bash
xattr -cr "/Applications/AI4HEOR.app"
```

En Windows, usa **More info -> Run anyway** en SmartScreen.

## Compilar desde el código

```bash
git clone https://github.com/ai4s-research/open-science
cd open-science
pnpm install
bash scripts/dev/fetch-opencode.sh
bash scripts/dev/fetch-uv.sh
pnpm --filter @ai4s/desktop tauri dev
pnpm --filter @ai4s/desktop tauri build
```

Comprobaciones:

```bash
pnpm test
pnpm typecheck
pnpm lint
```

## Seguridad y privacidad

Los archivos del workspace, datos crudos, historial, procedencia, notebooks y run records permanecen locales por defecto. La ejecución de comandos, borrado de archivos, instalación de dependencias y conexiones remotas pasan por aprobación humana. Las credenciales se guardan en configuración privada de la app, no en el workspace, procedencia, git, exportaciones ni configuración global de OpenCode.

## Estructura del repositorio

| Ruta | Propósito |
| --- | --- |
| `apps/desktop/` | App de escritorio Tauri + React. |
| `packages/sdk/` | `OpenCodeClient`, la capa que evita llamadas directas desde la UI a OpenCode. |
| `packages/shared/` | Tipos compartidos y paleta de gráficos. |
| `runtime/skills/core/` | Skills científicos propios. |
| `runtime/skills/external/` | Caché opcional de revisión para candidatos externos; no se incluye por defecto. |
| `examples/` | Workspaces de ejemplo incluidos. |
| `scripts/dev/` | Fetchers de sidecar, `uv`, skills y pruebas enfocadas. |
| `docs/` | Notas de producto, técnica, operator, conectores e investigación. |

## Estado

El registro de implementación más fiable es [`PROGRESS.md`](./PROGRESS.md). El trabajo cercano se centra en builds firmados/notarizados, verificación Windows/Linux, auto-update, endurecimiento de conectores y revisión de reproducibilidad. Para discutir el proyecto, únete al [Open Science Discord](https://discord.gg/fWNMDKcd5P).

[MIT](./LICENSE). Open Science Desktop es tooling beta de investigación: trata las salidas como borradores y verifica números, citas, código y conclusiones antes de publicar o decidir.

## Cita

Si usas Open Science Desktop en tu investigación, cítalo así:

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

El botón **“Cite this repository”** de GitHub (generado desde [`CITATION.cff`](./CITATION.cff)) ofrece la misma referencia en APA y BibTeX.
