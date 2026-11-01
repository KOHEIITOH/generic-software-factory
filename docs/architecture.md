# アーキテクチャ — Generic Software Factory v0.2

## 1. 製品の定義

Generic Software Factoryは、ソフトウェア開発の計画・実行・品質・承認・成果物を統制する、AI-Nativeな独立開発プラットフォームです。

FactoryはAIサービス、Coding Agent、IDE拡張機能、Agent Frameworkの一部ではありません。人間とAIの両方が利用でき、Factory自身も外部または内蔵のAgent Runtimeを利用して開発作業を進めます。

**Factoryが開発プロセスの制御主体であり、AIは交換可能な実行能力の一つです。**

最初の製品スコープはソフトウェア開発に限定します。将来的な汎用業務自動化は、実証された開発機能を不必要に一般化しない範囲で検討します。

## 2. 基本的な関係

Factoryには、独立した2つの接続方向があります。

1. **Factoryへの入口（Inbound Interfaces）** — 人間や外部AI・システムがFactoryに指示し、状態を確認する。
2. **Factoryからの委譲（Outbound Agent Runtimes）** — FactoryがAgent Runtimeに作業を委譲し、その実行を監督する。

この2つを同じ「Agent Adapter」に混在させません。

### 2.1 Factoryへの入口

- CLI: 人間やスクリプトからの操作。
- MCP Server: MCP対応AIがFactoryの機能をToolとして利用する入口。
- API / SDK: 外部アプリケーションや自動化基盤からのプログラム操作。
- Notification / Trigger Adapter: Slackなどからのイベント受付。初期MVPでは対象外。

すべての入口は、共通のApplication Service / Use Caseを通じてFactory Coreを利用します。CLIやMCP ServerがWorkflow状態を直接変更してはいけません。

### 2.2 FactoryからのAgent実行

FactoryはAgent Runtime Adapterを通じて、Coding Agentや独自Agentに作業を委譲します。

想定する接続対象は次のとおりです（対応を保証する一覧ではなく、Adapter設計の検証対象です）。

- GitHub Copilot SDK / CLI
- OpenAI Codex SDK / CLI
- Claude Code / Claude Agent SDK
- Gemini CLI / Google Agent系Runtime
- OpenHands、Devin等の外部Coding Agent
- Strands Agents、LangGraph等で構築したCustom Agent
- 将来のAWS BedrockベースのCustom Agent

SDK、CLI、HTTP API、Framework組み込みなど接続方式は異なります。共通契約は共通化しますが、製品固有の能力や制約を隠しません。

## 3. 設計原則

| 原則 | 必須の性質 |
|---|---|
| Factory is Independent | Factoryは特定のAI製品やAIホストの内部に依存しない。 |
| Human & AI Accessible | 人間とAIの両方が、認可された入口からFactoryを操作できる。 |
| AI is Pluggable | Agent RuntimeとModel Providerは交換可能なAdapterとして扱う。 |
| Core Owns Orchestration | Task、Workflow、承認、Policy、再試行、監査の正本はFactory Coreが持つ。 |
| Capability-Aware | Runtimeごとの能力差を明示し、未対応機能を暗黙に成功扱いしない。 |
| Project Agnostic | 言語・フレームワーク・リポジトリ固有の規約はProject Configuration / Harnessに置く。 |
| Secure by Default | 最小権限、隔離実行、明示的な承認、監査可能性を標準とする。 |
| Evidence-Based Quality | Agentの自己申告だけでQuality Gateを通過させない。 |

## 4. 論理アーキテクチャ

```text
 Human / External AI / Automation
       |          |          |
      CLI        MCP       API / SDK
       |          |          |
       +----------+----------+
                  |
        Inbound Interface Layer
                  |
        Application Services
                  |
+----------------------------------------------+
|                 FACTORY CORE                 |
| Task / Workflow / Run / Release coordination |
| Policy / Approval / Retry / Recovery / Audit |
+----------------------------------------------+
       |             |              |
       v             v              v
 Agent Runtime   Source Control   Execution
    Adapter         Adapter        Adapter
       |             |              |
       v             v              v
 Copilot /       Git Provider     Docker /
 Codex / Claude                   Worktree
 Custom Agent
       |
       v
 Model Provider (optional / runtime-owned)
 Bedrock / OpenAI / Anthropic / Gemini

 Project Bootstrapper:
 repository discovery, project profile and harness proposals

 Knowledge / Harness:
 requirements, architecture, conventions, role instructions

 Quality:
 deterministic checks, evidence collection, independent review
```

### 4.1 Factory Core

Coreが所有する責務:

- Task、Workflow Run、Releaseのライフサイクルと関係。
- Workflow状態遷移、依存関係、並列実行、再試行、タイムアウト、キャンセル、再開。
- Policy評価、承認要求、承認状態。
- Agent Runtimeへの委譲と実行結果の正規化。
- 実行イベント、判断、成果物参照の監査記録。
- Quality Gateの判定と証拠の追跡。

CoreはCopilot、Bedrock、GitHub、Jira、Docker等の具体的SDKを直接importしてはいけません。

### 4.2 Inbound Interface Layer

CLI、MCP Server、API / SDKは、FactoryのApplication Serviceを呼び出す薄い入口です。

共通のユースケース例:

- projectの登録・検証・診断
- taskの作成・実行依頼
- run / task / releaseの状態取得
- 承認・差し戻し
- cancel / resume
- 実行ログ・成果物参照の取得

MCP ServerはFactoryの操作をAIに公開するための入口です。MCP自体がWorkflow EngineやAgent Runtimeになるわけではありません。MCP経由の操作にもCLI/APIと同じ認証・認可・Policyを適用します。

### 4.3 Agent Runtime Adapter

Factoryから外部または内蔵Agentに作業を委譲するOutbound Adapterです。

RuntimeごとにSDK、CLI、HTTP API、Frameworkなどの接続方法を選べます。Coreは実装方式を知りません。

共通契約の候補:

- start: taskとスコープ付きcontextを渡して実行を開始する。
- getStatus: 実行状態を取得する。
- getEvents: ログ・進捗・構造化イベントを取得する。
- cancel: 実行を停止する。
- getResult: 最終結果と成果物参照を取得する。
- resume: 対応Runtimeのみ、中断した実行を再開する。

Runtimeはcapabilitiesを宣言します。例: streaming、resume、subagents、tool restrictions、permission callbacks、structured output。未対応のcapabilityがWorkflowで必須なら、開始前に拒否します。

### 4.4 Model Provider Adapter

Model ProviderはAgent Runtimeとは別の概念です。

- Agent Runtime自身がモデル接続を所有する場合、FactoryはModel Provider Adapterを必要としません。
- FactoryがCustom Agentを実行し、モデル推論だけを外部化する場合、Bedrock / OpenAI / Anthropic / Gemini等のModel Provider Adapterを利用できます。
- Agent RuntimeとModel Providerを同一製品・同一ベンダーと仮定しません。

### 4.5 その他のAdapter

- Source Control: repository、branch / worktree、diff、commit、PR。
- Execution: Docker等の隔離workspace、コマンド実行、resource / network制限。
- Knowledge: Requirements、Architecture、Harness、Project Profile。
- Observability: logs、metrics、traces、artifact references。
- Ticket / Notification / Deployment: 必要になった段階で追加する任意Adapter。

### 4.6 Project Bootstrapper

既存プロジェクトと新規プロジェクトの初期化を支援します。

- Existing Project Mode: repository、言語、framework、依存、構造、CI、Docker、規約を分析し、Project ProfileとHarnessの変更案を作る。
- Greenfield Mode: 要求から技術選定、アーキテクチャ、Harness、初期構成の案を作る。
- Re-Discovery: 既存設定と実際のrepositoryの差分を検出する。

Bootstrapperは分析工程を統制します。AIによる分析・生成結果は提案として扱い、重要な設定・Harness変更はレビュー対象にします。

## 5. ドメインモデル

以下の概念を分離します。

- **Task**: 実行すべき仕事と受け入れ条件。
- **Workflow**: Taskを処理する手順・依存関係・分岐。
- **Run**: Workflowの1回の実行インスタンス。
- **Release**: 1つ以上のTask / PR / milestoneをまとめるリリース単位。初期MVPでは最小限の扱いとし、TaskやRunと同一視しない。
- **Approval**: 特定の操作・遷移に対する人間の判断。
- **Artifact**: diff、test report、review、log、PRなどの成果物参照。

外部チケット管理は必須ではありません。Factory内部Taskを正本にでき、Jira等との同期は任意Adapterとします。

## 6. Workflowのライフサイクル

MVPの代表的な状態:

`CREATED → VALIDATING → PLANNING → PLAN_READY → IMPLEMENTING → TESTING → REVIEWING → DELIVERY_READY → COMPLETED`

必要に応じて `WAITING_FOR_APPROVAL`、`WAITING_FOR_INPUT`、`BLOCKED`、`RETRYING`、`FAILED`、`CANCELLED` を使います。

状態名は実装時に厳密な状態機械として定義します。PR作成・Merge・DeployはWorkflowとPolicyにより別々に制御します。

すべての遷移についてrun/task ID、前後の状態、実行者、timestamp、理由、証拠・成果物参照、Policy判断を記録します。

## 7. 自律性と安全性

Autonomous by Default / Human-on-the-loopを目指します。AIが判断できる低リスク作業は自動で進め、重要な仕様判断・危険操作・Policy上の承認点だけ人間にエスカレーションします。

初期Policy:

- 調査、計画案、Task分解、隔離workspace内のコード変更、テスト、レビュー: 自動実行可能。
- PR作成: プロジェクトPolicyで許可された場合に自動実行可能。
- Merge、本番Deploy、破壊的DB変更、権限・Security Policy変更: 人間承認必須。
- 会社のAI利用Policy、Runtimeの利用許可、Secret取り扱い、ネットワーク制限を優先する。

信頼できないコードは隔離環境で実行し、本番SecretをAgentに渡さず、直接Merge / Production Deployを禁止し、すべての重要な操作を監査可能にします。

## 8. MVPの実装方針

最初の実証では、全Adapterや全Interfaceを実装しません。

- Inbound: Local CLIのみ。
- Outbound: まず1つのCoding Agent Runtime。
- Runtime候補: GitHub Copilot SDK / CLIを第一実証候補とする。実際のSDK利用条件・会社の利用許可・実行方式を確認して選択する。
- Project: 既存のKotlin / Spring Boot Backend repositoryを1つ。
- Execution: Dockerまたは承認された隔離workspace。
- Source Control: 既存Git providerの最低限のbranch / diff操作。
- Quality: 既存Gradle test等の決定的コマンドとAI review。
- Delivery: PR作成可能な状態まで。自動Merge / Deployは行わない。
- MCP Server、Slack、Jira、複数Repository、複数Runtimeの同時実行は次段階。

実装言語はまだ確定しません。Copilot SDK、Codex SDK、Claude Agent SDK、Strands、CLI/API接続の実証結果、会社PCの制約、保守性を比較してから決定します。Runtime Adapterの境界は言語非依存で先に定義します。

## 9. 対象外

- Factoryを特定AIサービスの内部でしか動かせない構造にすること。
- 特定のAgent FrameworkをCoreの必須依存にすること。
- すべてのAgentを同じ機能・権限を持つものとして扱うこと。
- 初期段階で汎用業務自動化プラットフォームを目指すこと。
- 人間の承認なしの本番Merge / Deploy。
- レビューなしのCore / Security Policyの自己変更。
