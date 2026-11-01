# MVP計画 — v0.3

## 1. MVPの目的

ローカルCLIからFactoryに開発タスクを依頼し、FactoryがプロジェクトのHarnessとコードを読み込み、Coding Agent Runtimeに実装を委譲し、隔離workspace内でテスト・レビューを実行して、PR作成可能な状態まで進められることを実証します。

最初の実証では、Codex CLIを利用します。主要Runtimeへの対応は段階的に追加しますが、初期段階で全Runtimeを同時実行したり、複雑なモデルルーティングを構築したりしません。

## 2. 最初の縦切りWorkflow

CLI → Task → Validate → Load Harness / Project Context → Plan → Implement → Test → Review → Delivery Ready

- CLIから自然言語の開発依頼を受け付ける。
- Project Profile、Requirements、Architecture、Harnessを読み込む。
- Agent Runtimeが作業計画を作成する。
- 専用branch / worktreeと隔離workspace内で実装する。
- プロジェクトの決定的なtest / lint / buildを実行する。
- 独立したレビュー工程を実行し、指摘と証拠を記録する。
- 変更差分、実行ログ、テスト結果、レビュー結果を人間に提示する。
- PR作成はSource Control AdapterとPolicyが整った場合に有効化する。初期実証の最低条件はPR作成可能な差分を安全に残せること。

## 3. 実装スコープ

### M0 — Contract / Architecture

- Factory CoreとInbound / Outbound境界を維持する。
- Agent RuntimeとModel Providerを区別する。
- 最小Runtime契約は execute(prompt, workspace, timeout) と正規化された結果に限定する。
- Runtime固有の機能差を無理に共通化しない。

### M1 — Codex Local Runtime

- Python CLI: sf doctor、sf codex-smoke。
- Codex CLI Adapter: 非対話実行、JSONL結果取得、終了コード、timeout。
- read-only smoke testを一時ディレクトリで実行する。
- 会社のソースコードやSecretは使用しない。

### M2 — Local Development Vertical Slice

- Task作成・実行・状態管理。
- Project Profile / Harnessの読込。
- 専用branch / worktreeと隔離workspace。
- workspace-writeの権限・承認設計。
- 決定的なtest / lint / buildと独立レビュー。
- 実行状態・ログ・成果物の永続化、timeout、retry、cancel。

### M3 — Runtime Portability

次のRuntime Adapterを順次追加し、同じTaskをCore変更なしで切り替えられることを検証する。

1. Claude Code
2. GitHub Copilot
3. Gemini CLI

各Runtimeの認証、実行、権限、ログ、timeout、cancelの実際の対応範囲を確認する。必要性が確認できた機能だけ共通契約に追加する。

### M4 — Model Provider / External Interfaces

- AWS Bedrock / xAI APIをCustom Agentからモデル推論を利用するModel Provider Adapterとして必要に応じて追加する。
- 必要に応じて他社Model APIを追加する。
- MCP Server、API / SDK、Slack等は開発Workflowの実証後に追加する。

## 4. 複雑化を防ぐ方針

- 自動Runtime選択・自動Model RoutingはMVP対象外。
- Agent Swarmや複数Agent同時協調はMVP対象外。
- すべてのRuntimeが同じcapabilityを持つ前提にしない。
- Agent Runtimeが内包するモデル接続をFactory側で無理に置き換えない。
- BedrockやxAI APIをCoding Agent Runtimeと同じ種類のAdapterにしない。
- Grok BuildはAgent Runtimeとして扱い、GrokモデルAPIとは区別する。
- 新しい抽象化は、2つ目の実装や具体的な利用要件が現れたときに追加する。

## 5. MVPの受け入れ条件

1. クリーンなcheckoutからローカル環境を診断できる。
2. CLIからTaskを作成・実行できる。
3. FactoryがAgent Runtimeにタスクを委譲し、結果を追跡できる。
4. AgentがPolicyに従った専用workspace内で変更を行う。
5. テスト等の決定的なQuality Gateが機械可読な証拠を生成する。
6. 独立レビューの結果を保存・表示できる。
7. run / task / artifact / Agent実行の関係を追跡できる。
8. cancel、timeout、失敗を安全に扱える。
9. MergeとProduction Deployは人間の承認なしに実行されない。
10. Runtime Adapterを交換するためにFactory Coreを変更する必要がない。
11. 会社のAI利用Policy・Secret管理・ネットワーク制約を満たす。

## 6. 初期実証で後回しにするもの

- 全Runtimeの同時実行とAgent Swarm。
- 自動モデル選択・自動Runtimeルーティング。
- Bedrock経由での任意モデルへの自動切替。
- MCP ServerとSlackからのTrigger。
- 複数Repositoryの同時実行。
- 自動Merge、本番Deploy。
- 汎用Web Dashboard。
