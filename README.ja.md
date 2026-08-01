<div align="center">

[![Open Science Desktop — Local-first AI research workbench](./docs/assets/banner.webp)](https://github.com/ai4s-research/open-science)

# Open Science Desktop

**macOS、Windows & Linux 向けのローカルファースト、モデル非依存 AI 研究ワークベンチ。**

Formerly Open Science. Claude Science などの AI-for-science ワークベンチに対するオープンソースのデスクトップ代替です。Tauri、MCP、agent skills、再現可能な成果物を基盤に、エージェント、ノートブック、ファイル、図、レポート、実行記録、レビューを 1 つの監査可能なデスクトップワークフローにまとめます。

<p>
  <a href="./README.md">English</a> ·
  <a href="./README.zh.md">简体中文</a> ·
  <b>日本語</b> ·
  <a href="./README.es.md">Español</a> ·
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

🎉 **評価:** Open Science Desktop は、自律型科学研究エージェント向けのエンドツーエンドベンチマーク [ResearchClawBench](https://internscience.github.io/ResearchClawBench-Home/) で、採点済みタスク平均スコア第 1 位です（Pass@1 リーダーボード、2026 年 7 月 9 日）。
この上流 Agent ベンチマークは、AI4HEOR の科学研究を Agent が主導すべきことや、その出力の有効性を証明するものではありません。

---

## 目次

- [✨ できること](#できること)
- [🎬 スクリーンショット](#スクリーンショット)
- [🧪 現在の機能](#現在の機能)
- [🔌 スキルとコネクタ](#スキルとコネクタ)
- [📦 インストール](#インストール)
- [🚀 ソースからビルド](#ソースからビルド)
- [🔒 安全性とプライバシー](#安全性とプライバシー)
- [🗂️ リポジトリ構成](#リポジトリ構成)
- [📌 状態](#状態)

## できること

**人間の研究者が主導する HEOR ワークフローを支援します**——研究者が定義した問いから、レビュー可能なエビデンス、決定論的分析、検証、報告成果物までを、監査可能な一連のセッションで扱います。

- **自然言語を優先した支援**: 研究者が作業を開始して制御し、モデル/ランタイムは権限を限定された手順を提案または実行します。科学的判断権は取得しません。
- **すべてが辿れる**: 図、表、レポート、ノートブック、実行出力は、それらを生成した正確なコード、入力、環境、モデル出力、会話へリンクします。
- **ローカルファースト、あなたのもの**: セッション、データ、来歴、ノートブック、実行記録はすべて手元のローカルフォルダに保存され、既定では外部に出ません。
- **モデル非依存ランタイム**: UI は `packages/sdk` 経由でバンドル済み OpenCode sidecar と通信します——好きなモデルを持ち込めます。プロバイダ、スキル、MCP サーバーは差し替え可能です。
- **設計から再現可能**: ローカル、SSH/Slurm、Modal、notebook-batch の実行を、散らばった端末ログではなく再現可能な run record として記録します。
- **統制された拡張性**: ファーストパーティ HEOR Skill、研究者が管理する MCP サーバー、`/` コマンド、`!` shell モード、モデル非依存 SDK。

## スクリーンショット

![ローカル保存、モデル選択、承認、Human の科学的権限を示す初回ガイド](./docs/audits/2026-07-17-first-use/06-skip-link-stable.png)

![HEOR 専用の自然言語スターター](./docs/audits/2026-07-17-first-use/07-heor-workspace-final.png)

![モデル実行前に編集できる費用対効果分析リクエスト](./docs/audits/2026-07-17-first-use/08-natural-language-draft-final.png)

## 現在の機能

**Open Science の研究基盤を維持し、境界を持つ HEOR Skill で強化します。** 53 個のファーストパーティ HEOR Skill と、ハッシュで固定された 7 個の MIT Open Science 汎用研究 Skill を同梱します。いずれも承認権や手法選択権を取得しません。

| スキル | 役割 | 主な成果物 |
| --- | --- | --- |
| `$heor-workbench` | 研究者主導の HEOR 作業を調整 | レビュー可能なローカル計画、成果物、停止点 |
| `$heor-local-evidence` | 自動通信せず、選択されたローカル知識ベースを棚卸し | ハッシュで結び付けたローカルエビデンス一覧 |
| `$heor-evidence-search` | Human の通信承認を要する PubMed/ClinicalTrials.gov 検索を作成 | 正確なリクエストハッシュとメタデータ候補 |
| `$literature-review` | プロジェクト内の書誌情報を取り込み、重複整理、検証、書き出し | 出典付き参考文献ライブラリと RIS、BibTeX、CSL-JSON 交換ファイル |
| `$heor-model-design` | 人間が定義した意思決定問題と概念モデルを構造化 | 意思決定問題・概念モデル成果物 |
| `$heor-decision-tree` | 研究者が選択した出典付き有限イベントツリーを実行 | 入力ハッシュに結び付いた短期費用、QALY、増分結果、計算トレース |
| `$heor-cohort-state-transition` / `$heor-partitioned-survival` | 境界付き決定論的経済モデルを実行 | 再現可能な費用、QALY、増分結果、検査 |
| `$heor-uncertainty-analysis` / `$heor-advanced-value-of-information` | 宣言済み不確実性分析と限定 VOI を実行 | DSA/PSA/CEAC/CEAF/EVPI と個別レビュー対象の高度 VOI |
| `$heor-budget-impact` / `$heor-dynamic-budget-impact` | 静的・動的予算影響分析を実行 | 内訳付き予算結果と監査成果物 |
| `$heor-model-validation` / `$heor-reporting` / `$heor-reproducibility-package` | 現在の正確な成果物を検証・報告・梱包 | 独立レビュー用パッケージ、報告書、再実行バンドル |
| `$research-presentation` | 出典に結び付いた発表内容を準備し、ローカルで生成 | 確認可能なマクロなし PPTX と生成監査記録 |
| `$research-tables` | 型、単位、出典を明示した研究用表を準備 | 確認可能な数式なし XLSX、表ごとの CSV、生成監査記録 |
| `$journal-submission-check` | 研究者が保存した公式投稿規定から明示的な形式要件を記録 | 出典に結び付き、研究者の確認待ちの点検報告 |

60 個すべての Skill の名称と説明は 7 言語で提供され、正確な `$skill-id` も表示されます。

### プラットフォーム

| 領域 | 現在の状態 |
| --- | --- |
| デスクトップ | Tauri 2 + React + TypeScript + Vite。macOS、Windows、Linux のビルド対象。 |
| ランタイム | アプリが自動起動するバンドル済み OpenCode sidecar。ユーザー自身の OpenCode 設定/データとは分離。 |
| セッション | 複数セッション、履歴、日時付きワークスペース、全ワークスペース履歴、`/` コマンド、`!` shell モード。 |
| ファイル | グローバル/セッション内のファイルブラウズ、右クリック操作、外部アプリで開く、パスコピー、ローカルプレビューサーバー。 |
| ノートブック | 実際の `.ipynb`、Python/R ノートブック作成、ローカルカーネル実行、バンドル `uv` による Jupyter 環境、JupyterLab 起動。 |
| 実行記録 | 追記型 run log、グローバル SQLite インデックス、検索/ファセット/ページング、出力リンク、ログ、再現プロンプト。 |
| 来歴 | `.openscience/provenance.jsonl` がファイル版を記録し、成果物を作成元の実行または編集へ結びます。 |
| ビューア | PDF、画像、動画、HTML、Markdown、コード、CSV/TSV とチャート、DOCX、XLSX、PPTX、分子、3D mesh、ゲノム、FITS、DOS/DOSCAR、EIGENVAL bands、qcode、異常マップ、phase。 |
| UI 言語 | English、简体中文、日本語、Español、Deutsch、Français、한국어。Portuguese (Brazil) と Arabic は登録済みですが、まだ選択可能ではありません。 |

## スキルとコネクタ

`runtime/skills/core/` の 53 個のファーストパーティ HEOR Skill と、固定コミットから取得して MIT ライセンスとツリーハッシュを検証した 7 個の Open Science 汎用研究 Skill を配布します。Anthropic の文書 Skill は再配布不可のため同梱しません。

Open Science の 7 個の研究コネクタ（Paper Search、BioMCP、Materials Project、FRED、Space Weather、Open-Meteo、USGS Water）は Settings からアプリ専用環境へ必要時にインストールできます。`$heor-evidence-search` は監査可能な HEOR 証拠検索経路として維持され、汎用コネクタの結果が自動的に採用証拠になることはありません。詳細は [`docs/CONNECT_YOUR_TOOLS.md`](./docs/CONNECT_YOUR_TOOLS.md) を参照してください。

## インストール

[Releases](https://github.com/ai4s-research/open-science/releases/latest) から最新版をダウンロードしてください。

- **macOS**: `.dmg` / `.app`、Apple Silicon と Intel、macOS 13 Ventura 以降。
- **Windows**: NSIS `.exe` と `.msi`、Windows 10/11 x64。
- **Linux**: x86_64 Linux 向け `.deb` と `.rpm`。

まだコード署名/Notarization はありません。macOS でブロックされた場合:

```bash
xattr -cr "/Applications/AI4HEOR.app"
```

Windows では SmartScreen の **More info -> Run anyway** を選択します。

## ソースからビルド

```bash
git clone https://github.com/ai4s-research/open-science
cd open-science
pnpm install
bash scripts/dev/fetch-opencode.sh
bash scripts/dev/fetch-uv.sh
pnpm --filter @ai4s/desktop tauri dev
pnpm --filter @ai4s/desktop tauri build
```

チェック:

```bash
pnpm test
pnpm typecheck
pnpm lint
```

## 安全性とプライバシー

ワークスペース、元データ、会話履歴、来歴、ノートブック、実行記録は既定でローカルに残ります。コマンド実行、削除、依存関係インストール、リモート接続は人間の承認を通ります。認証情報はアプリ専用ランタイム設定に保存され、ワークスペース、来歴、git、エクスポート、グローバル OpenCode 設定には入りません。

## リポジトリ構成

| パス | 用途 |
| --- | --- |
| `apps/desktop/` | Tauri + React デスクトップアプリ。 |
| `packages/sdk/` | `OpenCodeClient`。UI が OpenCode を直接呼ばないための層。 |
| `packages/shared/` | 共有型とチャートパレット。 |
| `runtime/skills/core/` | 第一者科学スキル。 |
| `runtime/skills/external/` | 外部候補用の任意レビューキャッシュ。既定ではバンドルされません。 |
| `examples/` | 内蔵サンプルワークスペース。 |
| `scripts/dev/` | sidecar、`uv`、スキル取得、回帰プローブ。 |
| `docs/` | 製品、技術、operator、コネクタ、研究メモ。 |

## 状態

現在の実装ログは [`PROGRESS.md`](./PROGRESS.md) を参照してください。近い作業は署名済みリリース、Windows/Linux 検証、自動更新、コネクタの堅牢化、再現性レビューの継続です。議論には [Open Science Discord](https://discord.gg/fWNMDKcd5P) も使えます。

[MIT](./LICENSE). Open Science Desktop は beta の研究ツールです。出力は草稿として扱い、公開や意思決定の前に数字、引用、コード、結論を検証してください。

## 引用

研究で Open Science Desktop を使用した場合は、以下のように引用してください:

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

GitHub の **“Cite this repository”** ボタン([`CITATION.cff`](./CITATION.cff) から生成)でも APA / BibTeX 形式を取得できます。
