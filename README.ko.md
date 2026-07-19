<div align="center">

[![Open Science Desktop — Local-first AI research workbench](./docs/assets/banner.webp)](https://github.com/ai4s-research/open-science)

# Open Science Desktop

**macOS, Windows & Linux용 로컬 우선, 모델 독립 AI 연구 워크벤치.**

Formerly Open Science. Claude Science 및 유사한 AI-for-science 워크벤치의 오픈소스 데스크톱 대안으로, Tauri, MCP, agent skills, 재현 가능한 산출물을 기반으로 합니다. 에이전트, 노트북, 파일, 그림, 보고서, 실행 기록, 리뷰를 하나의 감사 가능한 데스크톱 워크플로로 연결합니다.

<p>
  <a href="./README.md">English</a> ·
  <a href="./README.zh.md">简体中文</a> ·
  <a href="./README.ja.md">日本語</a> ·
  <a href="./README.es.md">Español</a> ·
  <a href="./README.de.md">Deutsch</a> ·
  <a href="./README.fr.md">Français</a> ·
  <b>한국어</b>
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

🎉 **인정:** Open Science Desktop은 자율 과학 연구 에이전트를 위한 엔드투엔드 벤치마크 [ResearchClawBench](https://internscience.github.io/ResearchClawBench-Home/)에서 채점된 작업 평균 기준 1위를 기록했습니다(Pass@1 리더보드, 2026년 7월 9일).
이 업스트림 Agent 벤치마크는 AI4HEOR 안의 과학 연구가 Agent 주도여야 한다거나 그 결과가 유효하다는 증거가 아닙니다.

---

## 목차

- [✨ 무엇을 하나요](#무엇을-하나요)
- [🎬 스크린샷](#스크린샷)
- [🧪 현재 기능](#현재-기능)
- [🔌 스킬과 커넥터](#스킬과-커넥터)
- [📦 설치](#설치)
- [🚀 소스에서 빌드](#소스에서-빌드)
- [🔒 안전과 개인정보](#안전과-개인정보)
- [🗂️ 저장소 구조](#저장소-구조)
- [📌 상태](#상태)

## 무엇을 하나요

**인간 연구자가 주도하는 HEOR 워크플로를 지원합니다** — 연구자가 정의한 질문부터 검토 가능한 근거, 결정론적 분석, 검증, 보고 산출물까지 하나의 감사 가능한 세션에서 다룹니다.

- **자연어 우선 지원**: 연구자가 작업을 시작하고 통제하며, 모델/런타임은 범위가 제한된 단계를 제안하거나 실행할 뿐 과학적 권한을 갖지 않습니다.
- **모든 것이 역추적됩니다**: 그림, 표, 보고서, 노트북, 실행 출력이 이를 생성한 정확한 코드, 입력, 환경, 모델 출력, 대화로 연결됩니다.
- **로컬 우선, 당신의 것**: 세션, 데이터, provenance, 노트북, 실행 기록이 모두 로컬 폴더에 저장되며 기본적으로 외부로 나가지 않습니다.
- **모델 독립 런타임**: UI는 `packages/sdk`를 통해 번들·고정된 OpenCode sidecar와 통신합니다. 원하는 모델을 가져오세요; provider, skill, MCP 서버는 교체 가능합니다.
- **설계상 재현 가능**: 로컬, SSH/Slurm, Modal, notebook-batch 실행을 흩어진 터미널 출력이 아니라 재현 가능한 run record로 기록합니다.
- **통제된 확장성**: 자체 HEOR Skill, 연구자가 관리하는 MCP 서버, `/` 명령, `!` shell 모드, 모델 독립 SDK.

## 스크린샷

![로컬 저장, 모델 선택, 승인, Human 과학 권한 경계를 설명하는 첫 사용 안내](./docs/audits/2026-07-17-first-use/06-skip-link-stable.png)

![HEOR 전용 자연어 시작 화면](./docs/audits/2026-07-17-first-use/07-heor-workspace-final.png)

![모델 실행 전에 편집 가능한 비용효과 요청](./docs/audits/2026-07-17-first-use/08-natural-language-draft-final.png)

## 현재 기능

**범위가 명확한 HEOR Skill 기반 지원.** 50개 자체 Skill은 연구자가 정의한 작업을 라우팅하지만 승인 권한이나 방법 선택 권한을 갖지 않습니다. 대표 워크플로:

| 스킬 | 역할 | 주요 산출물 |
| --- | --- | --- |
| `$heor-workbench` | 연구자 주도의 HEOR 작업 조정 | 검토 가능한 로컬 계획, 산출물, 중지 지점 |
| `$heor-local-evidence` | 자동 네트워크 없이 선택된 로컬 지식베이스 목록화 | 해시로 연결된 로컬 근거 인벤토리 |
| `$heor-evidence-search` | Human 네트워크 승인이 필요한 PubMed/ClinicalTrials.gov 검색 준비 | 정확한 요청 해시와 메타데이터 후보 |
| `$literature-review` | 프로젝트 참고문헌 정보 가져오기, 중복 정리, 검증, 내보내기 | 출처 기록 참고문헌 라이브러리와 RIS, BibTeX, CSL-JSON 교환 파일 |
| `$heor-model-design` | 인간이 정의한 의사결정 문제와 개념 모델 구조화 | 의사결정 문제 및 개념 모델 산출물 |
| `$heor-cohort-state-transition` / `$heor-partitioned-survival` | 범위가 제한된 결정론적 경제 모델 실행 | 재현 가능한 비용, QALY, 증분 결과와 검사 |
| `$heor-uncertainty-analysis` / `$heor-advanced-value-of-information` | 선언된 불확실성과 제한된 VOI 실행 | DSA/PSA/CEAC/CEAF/EVPI 및 별도 검토 고급 VOI |
| `$heor-budget-impact` / `$heor-dynamic-budget-impact` | 정적 또는 동적 예산영향 분석 실행 | 세분화된 예산 결과와 감사 산출물 |
| `$heor-model-validation` / `$heor-reporting` / `$heor-reproducibility-package` | 현재의 정확한 산출물 검증·보고·패키징 | 독립 검토 패키지, 보고서, 재실행 번들 |
| `$research-presentation` | 출처에 연결된 발표 내용을 준비하고 로컬에서 생성 | 검토 가능한 매크로 없는 PPTX와 생성 감사 기록 |

50개 자체 Skill의 이름과 설명은 정확한 `$skill-id`를 유지한 채 7개 UI 언어로 제공됩니다. 외부 자산은 개별 승인 전까지 비활성입니다.

### 플랫폼

| 영역 | 현재 상태 |
| --- | --- |
| 데스크톱 | Tauri 2 + React + TypeScript + Vite, macOS/Windows/Linux 빌드 대상. |
| 런타임 | 앱이 자동 시작하는 번들 OpenCode sidecar. 사용자의 OpenCode 설정/데이터와 격리됩니다. |
| 세션 | 다중 세션 채팅/히스토리, 날짜별 워크스페이스 폴더, 전역 히스토리, `/` 명령, `!` shell 모드. |
| 파일 | 전역/세션 파일 탐색, 컨텍스트 메뉴, 외부 열기/표시, 경로 복사, 로컬 미리보기 서버. |
| 노트북 | 실제 `.ipynb`, Python/R 노트북 생성, 로컬 커널 실행, 번들 `uv` 기반 Jupyter 환경, JupyterLab 열기. |
| 실행 기록 | append-only run log, 전역 SQLite 인덱스, 검색/필터/페이지네이션, 로컬/원격 surface, 출력 링크, 로그, 재현 prompt. |
| Provenance | `.openscience/provenance.jsonl`이 파일 버전을 기록하고 산출물을 생성한 실행 또는 편집과 연결합니다. |
| 뷰어 | PDF, 이미지, 비디오, HTML, Markdown, 코드, CSV/TSV와 차트, DOCX, XLSX, PPTX, 분자, 3D mesh, genome, FITS, DOS/DOSCAR, EIGENVAL bands, qcode, anomaly map, phase 파일. |
| UI 언어 | English, 简体中文, 日本語, Español, Deutsch, Français, 한국어. Portuguese (Brazil)와 Arabic은 등록되어 있지만 아직 선택할 수 없습니다. |

## 스킬과 커넥터

기본 배포에는 `runtime/skills/core/`의 자체 Skill만 포함됩니다. 외부 자산은 라이선스, 경계, 테스트, 검토, 크로스 플랫폼 증거와 정확한 해시를 통과할 때까지 비활성입니다. Anthropic 문서 Skill은 재배포 금지 라이선스로 인해 거부되었습니다.

기본 화면은 검토되지 않은 외부 MCP를 원클릭으로 시작하지 않습니다. `$heor-evidence-search`는 Human이 명시적으로 승인한 뒤 고정된 PubMed·ClinicalTrials.gov 메타데이터 엔드포인트만 사용하며, Jupyter만 관리형 원클릭 로컬 계산 도구입니다. Settings에서 추가한 MCP는 관리되지 않는 외부 기능으로 표시되고 과학적 판단이나 승인 권한을 얻지 않습니다. [`docs/CONNECT_YOUR_TOOLS.md`](./docs/CONNECT_YOUR_TOOLS.md)를 참조하세요.

## 설치

[Releases](https://github.com/ai4s-research/open-science/releases/latest)에서 최신 설치 파일을 받으세요.

- **macOS**: `.dmg` / `.app`, Apple Silicon 및 Intel, macOS 13 Ventura 이상.
- **Windows**: NSIS `.exe` 및 `.msi`, Windows 10/11 x64.
- **Linux**: x86_64용 `.deb` 및 `.rpm`.

아직 코드 서명/공증이 없습니다. macOS에서 앱이 차단되면:

```bash
xattr -cr "/Applications/AI4HEOR.app"
```

Windows에서는 SmartScreen에서 **More info -> Run anyway**를 선택합니다.

## 소스에서 빌드

```bash
git clone https://github.com/ai4s-research/open-science
cd open-science
pnpm install
bash scripts/dev/fetch-opencode.sh
bash scripts/dev/fetch-uv.sh
pnpm --filter @ai4s/desktop tauri dev
pnpm --filter @ai4s/desktop tauri build
```

검사:

```bash
pnpm test
pnpm typecheck
pnpm lint
```

## 안전과 개인정보

워크스페이스 파일, 원본 데이터, 세션 히스토리, provenance, 노트북, run record는 기본적으로 로컬에 남습니다. 명령 실행, 파일 삭제, 의존성 설치, 원격 연결은 사용자 승인을 거칩니다. 자격 증명은 앱 전용 런타임 설정에 저장되며 워크스페이스, provenance, git, export, 전역 OpenCode 설정에는 들어가지 않습니다.

## 저장소 구조

| 경로 | 용도 |
| --- | --- |
| `apps/desktop/` | Tauri + React 데스크톱 앱. |
| `packages/sdk/` | UI가 OpenCode를 직접 호출하지 않도록 하는 `OpenCodeClient`. |
| `packages/shared/` | 공유 타입과 차트 팔레트. |
| `runtime/skills/core/` | First-party 과학 스킬. |
| `runtime/skills/external/` | 외부 후보를 위한 선택적 검토 캐시이며 기본 번들에는 포함되지 않습니다. |
| `examples/` | 내장 예제 워크스페이스. |
| `scripts/dev/` | sidecar, `uv`, skill fetcher 및 집중 회귀 검사. |
| `docs/` | 제품, 기술, operator, connector, research notes. |

## 상태

가장 신뢰할 수 있는 구현 로그는 [`PROGRESS.md`](./PROGRESS.md)입니다. 가까운 작업은 서명/공증된 릴리스, Windows/Linux 검증 확대, 자동 업데이트, 커넥터 강화, 재현성 리뷰 지속입니다. 토론은 [Open Science Discord](https://discord.gg/fWNMDKcd5P)에서도 할 수 있습니다.

[MIT](./LICENSE). Open Science Desktop은 beta 연구 도구입니다. 출력은 초안으로 보고, 공개나 의사결정 전에 숫자, 인용, 코드, 결론을 검증하세요.

## 인용

연구에서 Open Science Desktop을 사용했다면 아래와 같이 인용해 주세요:

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

GitHub의 **“Cite this repository”** 버튼([`CITATION.cff`](./CITATION.cff) 기반)에서 APA/BibTeX 형식도 얻을 수 있습니다.
