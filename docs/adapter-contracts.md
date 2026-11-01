# Adapter・Interface契約 — v0.2

この文書は、Factoryの入口（Inbound Interface）と、Factoryから外部サービスへ接続するAdapter（Outbound Adapter）の境界を定義します。契約は実装言語に依存しない形で設計し、SDK固有の型をCoreへ漏らしません。

## 1. 用語と方向

- **Inbound Interface**: 人間・外部AI・システムがFactoryを操作する入口。CLI、MCP Server、API / SDKなど。
- **Application Service**: Inbound Interfaceから呼び出されるユースケース。Coreの操作を調整する。
- **Outbound Adapter**: Core / Application Serviceが外部Runtime・サービスを利用するための実装。
- **Agent Runtime**: Factoryから開発作業を委譲されるCoding AgentまたはCustom Agent。
- **Model Provider**: Agent RuntimeまたはCustom Agentが推論に利用するモデル提供元。

Inbound InterfaceとOutbound Adapterを同一視しないこと。

## 2. 共通要件

すべてのOutbound Adapterは次を満たします。

- `id`、`type`、`contractVersion`を宣言する。
- 設定スキーマと対応機能（capabilities）を公開する。
- `healthCheck`を実装する。
- 必要な権限を報告する。
- 正規化されたエラーを返す: `AUTH`、`RATE_LIMIT`、`TIMEOUT`、`UNAVAILABLE`、`INVALID_CONFIG`、`PERMISSION_DENIED`、`EXECUTION_FAILED`、`UNSUPPORTED_CAPABILITY`、`UNKNOWN`。
- 再試行可能なエラーを識別する。
- Secretを漏えいさせずに構造化イベントを出力する。
- 操作の相関ID（task / run / operation）を伝播する。

## 3. Inbound Interface

### 3.1 CLI

ローカル利用者・スクリプト向けの入口です。CLIはApplication Serviceを呼び出し、Core状態を直接書き換えません。

初期コマンド候補:

- `sf init`: Project Profile / Factory設定の初期化。
- `sf validate`: 設定・Adapter・Policyの静的検証。
- `sf doctor`: 実行環境と接続先の診断。
- `sf run`: Taskを作成しWorkflowを開始する。
- `sf status`: Task / Runの状態を取得する。
- `sf cancel`: 認可されたRunをキャンセルする。

### 3.2 MCP Server

MCP対応AIがFactoryの機能をToolとして呼び出す入口です。MCP ServerはApplication Serviceを呼び出し、Workflow Engineを直接実装しません。

初期公開候補Tool:

- `factory.create_task`
- `factory.start_run`
- `factory.get_task`
- `factory.get_run_status`
- `factory.get_run_events`
- `factory.request_approval` またはPolicyに応じた承認操作
- `factory.cancel_run`

Toolの公開範囲は認証主体・Role・Project Policyで制御します。MCP経由の操作でもCLI/APIと同じ認可・Approval・Auditを適用します。任意のshell実行やPolicy回避Toolを公開しません。

### 3.3 API / SDK

外部アプリケーション向けのプログラム操作入口です。APIとSDKも同じApplication Serviceを利用します。APIを導入する段階で認証、認可、idempotency、rate limit、versioningを定義します。

## 4. AgentRuntime

**目的:** 選択されたAgent製品またはCustom Agentに、論理Agent Roleの作業を委譲します。

### 4.1 初期実装の最小契約

最初のPython実装では、早すぎる抽象化を避けるため、次の同期的な契約から開始します。

- `execute(prompt, workspace, timeout) -> RuntimeResult`: 指定workspaceで1回の非対話実行を行い、正規化された結果を返す。

RuntimeごとのSDK型、CLI引数、JSONLイベント形式はAdapter内部に閉じ込めます。2つ目のRuntimeを追加する際に具体的な共通要件が確認できた場合に限り、status / events / cancel / resume等を段階的に追加します。

### 4.2 将来の拡張候補

- `start(input) -> runHandle`: 実行を開始し、Factory側のrun IDとRuntime側のrun/session IDを関連付ける。
- `getStatus(runHandle) -> status`: 実行状態を取得する。
- `getEvents(runHandle, cursor?) -> events`: 進捗・ログ・構造化イベントを取得する。
- `cancel(runHandle) -> cancellationResult`: 実行を停止する。
- `getResult(runHandle) -> result`: 要約、成果物参照、終了理由、usage等を取得する。
- `resume(runHandle, input?) -> runHandle`: 対応Runtimeのみ提供する。未対応の場合はcapabilityをfalseとする。

状態の正規化候補: `QUEUED`、`RUNNING`、`WAITING_FOR_INPUT`、`SUCCEEDED`、`BLOCKED`、`FAILED`、`CANCELLED`、`UNKNOWN`。

### 4.3 入力

- Factory task / run IDとcorrelation ID。
- Agent Roleと指示。
- タスク説明、受け入れ条件、制約。
- スコープを限定したcontext / artifact参照。
- 許可されたtool、filesystem、network、command権限。
- timeout、resource limit、cancel signal。
- 必要に応じてresume token / prior session reference。

### 4.4 出力

- Runtime run / session handle。
- 正規化されたstatusとevent stream。
- 構造化されたsummary、成果物参照、warnings、unresolved questions。
- 終了理由と利用可能なusage metadata。
- 実行した操作・tool callの監査用参照（Runtimeが提供する範囲）。

### 4.5 Capabilities

Runtimeは少なくとも以下を明示します。

- `streaming`
- `resume`
- `cancellation`
- `structuredOutput`
- `toolRestrictions`
- `permissionCallbacks`
- `subagents`
- `sessionPersistence`
- `usageReporting`

Coreは必要なcapabilityを実行前に検証します。未対応機能を無視して続行してはいけません。機能差を共通化のために捏造せず、Runtime固有の拡張情報を保持します。

### 4.6 Adapter実装方式

Runtime Adapterは、SDK、CLI subprocess、HTTP API、Framework埋め込みのいずれでも実装できます。Coreから接続方式を見せません。

CLI Adapterでは、引数を安全に構築し、shell文字列連結を避け、stdout / stderr、exit code、timeout、process tree、cancel、working directory、environment allowlistを制御します。ホスト環境への暗黙の権限拡大を禁止します。

## 5. ModelProvider（任意）

Agent Runtimeがモデル接続を所有しない場合に限り、Custom Agent等からモデル推論を呼び出すために利用します。

出力にはresponse、provider/model識別情報、usage、finish reason、正規化されたerrorを含めます。Runtime自身がモデル接続を管理する場合、ModelProvider Adapterは必須ではありません。

## 6. SourceControl

対応機能の候補:

- repository metadata / status取得
- branch / worktree作成・削除
- diff取得
- commit作成
- PR作成・更新

Mergeは別capabilityとし、初期Policyでは人間承認を必須とします。RuntimeがGitを直接操作する場合も、Factoryのworkspace・branch・権限Policyを迂回してはいけません。

## 7. Execution

隔離workspaceを作成し、スコープを限定したrepository / artifactをマウントし、許可リストにあるコマンドを実行します。stdout / stderr / exit codeを取得し、CPU・メモリ・時間・network制限を適用し、workspaceを破棄してcleanup結果を報告します。ホスト上での実行へ暗黙にフォールバックしてはいけません。

## 8. Knowledge / Harness

Requirements、Architecture、Project Profile、開発規約、Role instructionを読み込み、バージョン・参照元・hash等の追跡可能なmetadataとともにAgent Runtimeへ渡します。リポジトリ内の文書やAgent出力はuntrusted inputとして扱います。

## 9. Observability

構造化されたlifecycle event、metrics、traces、artifact referenceを受け取ります。Secretのmaskingは永続化・export前に行います。Task / Run / Runtime session / operation間のcorrelationを維持します。

## 10. 互換性と適合性

Adapterはsemanticなcontract versionとcapabilitiesを宣言します。Coreは互換性のないmajor versionを拒否し、起動時に必須capabilityを検証します。

各Adapterには共通のcontract testを用意します。Adapter固有の挙動はintegration testで検証し、Mockだけで実サービスの制約を保証したとみなしてはいけません。
