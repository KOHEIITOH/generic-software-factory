# Generic Software Factory

**AI-Native Software Development Platform — 汎用AIソフトウェア開発プラットフォーム**

Generic Software Factoryは、ソフトウェア開発の計画・実行・品質・承認・成果物を統制する独立した開発プラットフォームです。人間とAIの両方がFactoryを利用でき、Factory自身も複数のAI Agent Runtimeを交換可能な実行手段として利用します。

> Factoryが開発プロセスの制御主体です。AIはFactoryの一部ではなく、Factoryが利用・統制する交換可能な能力です。

## 基本コンセプト

- **Factory is Independent** — Factoryは特定のAIサービスやAIホストの内部に依存しない。
- **Human & AI Accessible** — 人間はCLI / Slack / APIから、AIはMCP / APIからFactoryを利用できる。
- **AI is Pluggable** — Copilot、Codex、Claude、BedrockベースのCustom AgentなどをAdapter経由で利用する。
- **Core Owns Orchestration** — Task、Workflow、Policy、Approval、Auditの正本はFactory Coreが持つ。
- **Development First** — まずソフトウェア開発に特化し、汎用業務自動化への拡張は実証後に検討する。

## アーキテクチャ

- **Inbound Interface**: CLI、MCP Server、API / SDKなど、Factoryを操作する入口。
- **Factory Core**: Task / Workflow / Run / Release、Policy、Approval、Retry、Auditを管理。
- **Agent Runtime Adapter**: FactoryからCoding AgentやCustom Agentへ開発作業を委譲。
- **Other Adapters**: Source Control、Execution、Knowledge、Observability、Model Provider等。
- **Project Bootstrapper / Harness**: 既存プロジェクトの分析、Project Profile、Requirements、Architecture、開発規約を管理。

重要な設計境界は、**Factoryへの入口（Inbound Interface）** と **FactoryからAIへの委譲（Outbound Agent Runtime）** を分離することです。MCP ServerはAIがFactoryを操作する入口であり、Copilot / Codex / Claude等はFactoryが作業を委譲するRuntimeです。

詳しくは[アーキテクチャ](docs/architecture.md)、[Adapter・Interface契約](docs/adapter-contracts.md)、[設定](docs/configuration.md)、[セキュリティ](docs/security.md)、[MVP計画](docs/mvp-plan.md)を参照してください。
初めての方向けに[利用ガイド (HTML)](docs/user-guide.html)も用意しています。

## MVPの方向性

最初はローカルCLIから既存のBackend repositoryを対象に、1つのCoding Agent Runtimeを使って実装・テスト・レビューまで進める縦切りを作ります。

- 最初のRuntime候補: GitHub Copilot SDK / CLI
- 将来の候補: OpenAI Codex、Claude Code、Gemini、AWS BedrockベースのCustom Agent
- 初期対象: Kotlin / Spring Boot Backend
- 初期入口: Local CLI
- 次段階: MCP Server、API / SDK、Slack等

**実装言語は未確定です。** Copilot、Codex、Claude、Bedrock / Strands等の接続Spikeと、会社PCの制約・保守性を比較してから決定します。

## 現在のステータス

**v0.2 — Architecture / MVP specification updated.** Factoryの独立性、Inbound / Outbound境界、Agent Runtimeの交換可能性、Copilot先行のローカル縦切り方針を文書化しています。CLI、MCP Server、Reference Adapter、実行Workflowはまだ実装済みとは限りません。実行可能性は実装・環境検証で確認します。

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
```

## コントリビューション

Core契約、セキュリティPolicy、Workflowの意味を変更する場合は、Architecture Decision Record (ADR)が必要です。
