# MVP計画 — v0.2

## 1. MVPの目的

ローカルCLIからFactoryに開発タスクを依頼し、Factoryが既存プロジェクトのHarnessとコードを読み込み、Coding Agent Runtimeに実装を委譲し、隔離workspace内でテスト・レビューを実行して、PR作成可能な状態まで進められることを実証します。

最初の対象は、既存のKotlin / Spring Boot Backend repositoryを1つとします。

**MVPは「FactoryがAIを使って開発する」縦切りを優先します。** MCP Server、Slack、Jira、複数Runtime、複数Repositoryの同時実行は初期実証の必須条件にしません。ただし、後から人間とAIの両方がFactoryを操作できるよう、Inbound InterfaceとOutbound Agent Runtimeを分離した設計にします。

## 2. 最初の縦切りWorkflow

`CLI → Task → Validate → Load Harness / Project Context → Plan → Implement → Test → Review → Delivery Ready`

- CLIから自然言語の開発依頼を受け付ける。
- Project Profile、Requirements、Architecture、Harnessを読み込む。
- Agent Runtimeが作業計画を作成する。
- Policyに従って必要な場合のみ計画承認を待つ。
- 専用branch / worktreeと隔離workspace内で実装する。
- プロジェクトの決定的なtest / lint / buildを実行する。
- 独立したレビュー工程を実行し、指摘と証拠を記録する。
- 変更差分、実行ログ、テスト結果、レビュー結果を人間に提示する。
- PR作成は利用可能なSource Control AdapterとPolicyが整った場合に有効化する。初期実証の最低条件はPR作成可能な差分を安全に残せること。

## 3. 実装スコープ

### M0 — Architecture / Contract

- FactoryをAIサービスの一部ではなく独立した開発プラットフォームと定義する。
- Inbound Interface（CLI / MCP / API）とOutbound Agent Runtimeを分離する。
- CoreがTask / Workflow / Policy / Approval / Auditを所有する。
- Agent Runtimeの共通契約とcapabilitiesを定義する。
- 実装言語はSDK検証後に決定する。

### M1 — Local CLI Vertical Slice

- CLI: `sf doctor`、`sf init`、`sf validate`、`sf run`、`sf status`、`sf cancel`。
- Project Bootstrap / Harness Loader: 既存プロジェクトの最低限の検出とコンテキスト読込。
- Agent Runtime Adapter: 最初のCoding Agentを1つ接続する。GitHub Copilot SDK / CLIを第一候補とし、利用条件と会社の利用許可を確認する。
- Source Control Adapter: status、diff、専用branch / worktree等の最低限の操作。
- Execution Adapter: Dockerまたは会社で承認された隔離実行環境。
- Workflow / Task: 状態遷移、Task作成、実行、停止、結果参照。
- Quality: 既存プロジェクトのGradle test / build等と独立レビュー。
- Audit: run、Agentイベント、実行コマンド、成果物参照を記録する。

### M2 — Reliability / Safety

- 実行状態の永続化とプロセス再起動後の状態確認。
- timeout、retry、cancel、可能な場合のresume。
- Secret redaction、最小権限、ネットワーク制限。
- Docker / workspaceのcleanupと失敗時の安全停止。
- 決定的なQuality Gateと失敗証拠。
- Policyに基づくApproval Gate。

### M3 — Runtime Portability

- 2つ目のRuntime Adapterを追加する（候補: Codex SDK / CLI、Claude Agent SDK / CLI）。
- Adapter contract testを作成する。
- 同一Taskを異なるRuntimeで実行し、Core変更なしで切り替えられることを検証する。
- AWS Bedrock / Strands等のCustom Agent Runtimeを追加候補として評価する。

### M4 — AI / External System Interface

- MCP Serverを実装し、外部AIからTask作成、run状態参照、承認などの認可された操作を可能にする。
- API / SDKを追加する。
- Slack、Jira、Sentry、AWS Deployment等は実証ニーズに応じてAdapter化する。

## 4. 最初のRuntime選定

最初はGitHub Copilotを有力候補とします。ただし、Copilot SDKを前提にFactory全体の設計・言語を固定しません。

実装着手前に次を確認します。

1. 会社アカウント・会社PCでCopilot SDK / CLIの利用が許可されているか。
2. SDKの利用条件、認証方式、利用可能な機能。
3. Factoryから実行・キャンセル・イベント取得・結果取得が可能か。
4. ファイル編集・コマンド実行・権限確認をどこまで制御できるか。
5. Copilot以外（Codex、Claude Code、Bedrock系）を追加する際に必要な共通契約。
6. 会社のソースコードを対象Agentに渡すことが社内Policy上許可されているか。

SDKで必要な制御ができない場合、CLI Adapterを代替候補とします。SDKとCLIのどちらも使える前提にはしません。

## 5. 言語選定ゲート

Python / TypeScriptを中心に、必要に応じてGo / Kotlinも比較します。個別SDKの対応言語だけで決めず、次の小さなSpikeで評価します。

- Copilot SDK / CLIの起動・認証・イベント取得・キャンセル。
- CodexまたはClaudeのSDK / CLIを同じRuntime契約で接続できるか。
- Bedrock / Strandsへの接続方法。
- subprocess、Docker、ファイルシステムの安全な制御。
- CLI開発、型安全性、テスト、配布、保守性。
- 会社PCの実行制約とチームの運用可能性。

評価後にADRで実装言語と初期Runtimeを決定します。言語選定が完了するまでは、ドメイン契約とアーキテクチャを言語非依存で維持します。

## 6. MVPの受け入れ条件

1. クリーンなcheckoutからローカル環境を診断できる。
2. 既存プロジェクトを登録し、HarnessとProject Contextを読み込める。
3. CLIからTaskを作成・実行できる。
4. FactoryがAgent Runtimeにタスクを委譲し、進捗と結果を追跡できる。
5. Agentが専用workspace内で変更を行う。
6. テスト等の決定的なQuality Gateが機械可読な証拠を生成する。
7. 独立レビューの結果を保存・表示できる。
8. run / task / artifact / Agent実行の関係を追跡できる。
9. cancel、timeout、失敗を安全に扱える。
10. MergeとProduction Deployは人間の承認なしに実行されない。
11. Runtime Adapterを交換するためにFactory Coreを変更する必要がない。
12. 会社のAI利用Policy・Secret管理・ネットワーク制約を満たす。

## 7. 初期実証で後回しにするもの

- MCP ServerとSlackからのTrigger。
- Jira等の外部Ticket連携。
- 複数Repositoryの同時実行。
- 複数Runtimeの同時協調・Agent Swarm。
- Release orchestrationの完全実装。
- 自動Merge、本番Deploy。
- 汎用Web Dashboard。
- Greenfieldプロジェクトの完全自動生成。

## 8. 明日のローカル実証チェック

### 事前確認

- [ ] 会社のAI利用Policyで対象リポジトリとAgent Runtimeの利用が許可されている。
- [ ] Gitのread / branch作成権限がある。
- [ ] Copilot SDKまたはCLIを会社アカウントで利用できる。
- [ ] Dockerまたは承認済み隔離実行環境が使える。
- [ ] AWS Bedrockは初期実証の必須条件にしない。
- [ ] 本番Secret・本番接続先を実行環境に渡さない。
- [ ] 作業対象はBEの専用branch / worktreeに限定する。

### 実証タスク

小さく、既存テストで検証可能で、外部影響のない変更を1件選びます。最初はDBスキーマ変更、決済フロー変更、Production接続を避けます。

### 成功条件

CLIから依頼し、Agentが変更を作成し、テスト・レビューの証拠をFactoryが記録し、人間が差分を確認できること。PR作成や完全自律実行は、環境・Policy・Adapterが整っている場合にのみ追加します。
