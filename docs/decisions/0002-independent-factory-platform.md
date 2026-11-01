# ADR 0002: Factoryを独立した開発プラットフォームとして定義する

- Status: Accepted
- Date: 2026-11-01
- Decision owners: Generic Software Factory maintainers

## Context

Generic Software Factoryは、Coding Agentを単に呼び出すCLIや、特定AIサービスの内部で動くAgentではなく、ソフトウェア開発の計画・実行・品質・承認・成果物を統制する基盤を目指す。

人間がCLIやSlack等からFactoryを操作するユースケースに加え、Claude、Copilot等の外部AIがMCP / APIを通じてFactoryを操作するユースケースがある。一方、Factory自身もCopilot、Codex、Claude Code、BedrockベースのCustom Agent等へ開発作業を委譲する。

これらは接続方向と責務が異なるため、単一のAgent Adapterとして扱うと境界が不明瞭になる。

## Decision

1. FactoryはAIサービスから独立した、ソフトウェア開発専用のプラットフォームとする。
2. 人間とAIの双方がFactoryを利用できるようにする。
3. Factoryへの入口（Inbound Interface）と、FactoryからAIへ作業を委譲するOutbound Agent Runtimeを分離する。
4. CLI / MCP Server / API / SDKはApplication Serviceを通じてFactory Coreを利用する。
5. Factory CoreがTask、Workflow、Run、Policy、Approval、Retry、Recovery、Auditの正本を所有する。
6. Agent RuntimeはSDK、CLI、HTTP API、Framework組み込み等のAdapterとして接続する。
7. Model ProviderはAgent Runtimeと別の概念として扱い、Runtime自身がモデル接続を所有する場合は必須としない。
8. Runtimeの能力差はcapabilitiesとして宣言し、未対応機能を暗黙に成功扱いしない。
9. 初期製品スコープはソフトウェア開発に限定する。汎用業務自動化への拡張は、実証済みの共通機能をもとに別途判断する。
10. 初期実証はローカルCLIと1つのCoding Agent Runtimeから始め、MCP Serverは次段階で実装する。

## Consequences

### Positive

- 特定AIベンダーやAIホストに依存しない。
- 外部AIからFactoryを操作するユースケースと、FactoryがAIを利用するユースケースを両立できる。
- CoreのWorkflow・Policy・AuditをAI Runtimeの機能差から独立させられる。
- SDK型・CLI型・API型のAgent Runtimeを段階的に追加できる。

### Trade-offs

- Inbound InterfaceとOutbound Agent Runtimeの両方の契約・認証・認可を設計する必要がある。
- Runtimeごとの能力差を管理する必要があり、完全に同一の実行体験は保証できない。
- MCP Server、API、複数Runtime対応は初期MVPの実装範囲を広げないよう段階導入する。

## Rejected alternatives

### AIホストの内部でFactoryを動かす

Factoryの制御主体が外部AIホストになり、AI製品・セッション・権限モデルへの依存が強くなるため採用しない。

### Factoryを単一の自作Agentとして実装する

外部Coding Agentを活用しづらくなり、特定のModel Provider / Frameworkへの依存が強くなるため採用しない。

### Inbound InterfaceとOutbound Runtimeを同じAdapterに統合する

操作方向、認証主体、ライフサイクル、権限モデルが異なるため採用しない。

## Follow-up

- Inbound Application Serviceの契約を定義する。
- Agent Runtime Adapterの契約とcapabilitiesを定義する。
- Copilot SDK / CLIを第一候補として接続Spikeを行う。
- Codex、Claude Code、Bedrock / Strandsの接続性を比較する。
- 言語選定は接続Spikeの結果に基づくADRで決定する。
- MCP ServerはCLIでCoreユースケースが動作した後に追加する。
