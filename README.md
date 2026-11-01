# Generic Software Factory

**AI-Native Software Development Platform — 汎用AIソフトウェア開発プラットフォーム**

Generic Software Factoryは、ソフトウェア開発の計画・実行・品質・承認・成果物を統制する独立した開発プラットフォームです。人間とAIの両方がFactoryを利用でき、Factory自身も複数のAI Agent Runtimeを交換可能な実行手段として利用します。

> Factoryが開発プロセスの制御主体です。AIはFactoryの一部ではなく、Factoryが利用・統制する交換可能な能力です。

## 基本コンセプト

- **Factory is Independent** — Factoryは特定のAIサービスやAIホストの内部に依存しない。
- **Human & AI Accessible** — 人間はCLI / Slack / APIから、AIはMCP / APIからFactoryを利用できる。
- **AI is Pluggable** — Codex、Claude Code、GitHub Copilot、Gemini CLI、Grok Build等を共通Adapter経由で利用する。
- **Core Owns Orchestration** — Task、Workflow、Policy、Approval、Auditの正本はFactory Coreが持つ。
- **Development First** — まずソフトウェア開発に特化し、汎用業務自動化への拡張は実証後に検討する。

## アーキテクチャ

- **Inbound Interface**: CLI、MCP Server、API / SDKなど、Factoryを操作する入口。
- **Factory Core**: Task / Workflow / Run / Release、Policy、Approval、Retry、Auditを管理。
- **Agent Runtime Adapter**: FactoryからCoding AgentやCustom Agentへ開発作業を委譲。
- **Model Provider Adapter**: 必要な場合にCustom Agent等からモデル推論を利用する接続先。AWS Bedrock、xAI API等を想定。
- **Other Adapters**: Source Control、Execution、Knowledge、Observability等。
- **Project Bootstrapper / Harness**: 既存プロジェクトの分析、Project Profile、Requirements、Architecture、開発規約を管理。

入口（Inbound Interface）とAIへの委譲（Outbound Agent Runtime）は分離します。MCP ServerはAIがFactoryを操作する入口であり、Codex / Claude Code等はFactoryが作業を委譲するRuntimeです。

詳しくは[アーキテクチャ](docs/architecture.md)、[Adapter・Interface契約](docs/adapter-contracts.md)、[Agent対応ロードマップ](docs/agent-runtime-roadmap.md)、[設定](docs/configuration.md)、[セキュリティ](docs/security.md)、[MVP計画](docs/mvp-plan.md)を参照してください。
初めての方向けに[利用ガイド (HTML)](docs/user-guide.html)も用意しています。

## 現在の実装方針

- Factory Core / Local CLI: Python 3.11+（初期開発はPython 3.13）
- Dependency / quality tools: uv、pytest、Ruff、Pyright、pip-audit
- 初期Agent Runtime: Codex CLI Adapter
- 追加予定: Claude Code、GitHub Copilot、Gemini CLI、Grok Build
- Model Provider: AWS Bedrock、xAI API等を将来の独立した接続先として追加
- 将来のWeb UI: TypeScript（React / Next.js候補）
- 初期検証: 一時ディレクトリ内の安全なCodex read-only smoke test。会社のソースコードは使用しない。

## Quickstart — macOS

Python 3.13、uv、Git、Codex CLIを用意し、Codexにログインしたうえで:

```bash
git clone https://github.com/KOHEIITOH/generic-software-factory.git
cd generic-software-factory
uv python install 3.13
uv sync --python 3.13 --extra dev
codex login
uv run sf doctor
uv run sf codex-smoke
```

Copilot SDK smoke testも試す場合は、追加依存をインストールします:

```bash
uv sync --python 3.13 --extra dev --extra copilot
copilot login
uv run sf copilot-smoke
```

詳細は[Mac向けローカルSmoke Test](docs/local-smoke-test.md)を参照してください。

## 現在のステータス

**v0.4 — Codex CLI Runtime spike.** 最小Agent Runtime契約、Codex CLI Adapter、read-only smoke testを追加しています。Factory Workflow、Repository編集の隔離実行、独立レビュー、PR作成、MCP Server、Web UIはまだ実装していません。

## セキュリティの基準

- 信頼できないコードは分離された実行環境内でのみ実行する。
- 最小権限の認証情報とSecret参照を使い、平文Secretを設定に保存しない。
- ネットワークアクセスは既定で制限する。
- Merge、本番Deploy、破壊的操作、Policy変更には人間の承認を必須とする。
- タスク入力、リポジトリ内容、ツール出力、モデル出力は信頼できないデータとして扱う。
- 決定的なQuality Gateを必須とする。Agent自身によるレビューだけでは不十分。

## リポジトリ構成

```text
core/          Coreの契約とライフサイクル仕様
adapters/      外部Runtime・サービスとのAdapter契約
harness/       再利用可能な指示、Policy、知識テンプレート
agents/        Agent製品に依存しないRole定義
workflows/     再利用可能なWorkflow定義
config/        デプロイ設定の例
quality/       Quality Gateの仕様とテンプレート
docs/          アーキテクチャ、契約、セキュリティ、ADR、ロードマップ
src/           Python Core / CLI / Runtime Adapter
```

## コントリビューション

Core契約、セキュリティPolicy、Workflowの意味を変更する場合は、Architecture Decision Record (ADR)が必要です。
