# Adapter契約 (Adapter contracts) — v0.1

この文書では、言語に依存しない契約を定義します。具体的なSDKインターフェースは、最初の実装時に仕様化します。

## 共通要件

すべてのAdapterは次を満たします。

- `id`、`type`、`contractVersion`を宣言する。
- 設定スキーマと対応機能を公開する。
- `healthCheck`を実装する。
- 必要な権限を報告する。
- 正規化されたエラーを返す: `AUTH`、`RATE_LIMIT`、`TIMEOUT`、`UNAVAILABLE`、`INVALID_CONFIG`、`PERMISSION_DENIED`、`EXECUTION_FAILED`、`UNKNOWN`。
- 再試行可能なエラーを識別する。
- Secretを漏えいさせずに構造化イベントを出力する。

## AgentRuntime

**目的:** 選択されたAgent製品／Runtimeを使って、論理Agent Roleを実行します。

入力: run/task ID、RoleとRoleの指示、タスクの説明と受け入れ条件、スコープを限定したコンテキスト／成果物への参照、許可されたツールと権限、タイムアウトとリソース制限。

出力: status (`SUCCEEDED`、`NEEDS_INPUT`、`BLOCKED`、`FAILED`)、構造化された要約、成果物への参照、利用可能な場合は使用量のメタデータ、警告、未解決の質問。

Adapterに与える権限は、run Policyで許可された範囲を超えてはいけません。

## ModelProvider (任意)

選択したAgentRuntimeがモデルアクセスを担わない場合に限り、モデルを直接推論するために使います。出力には、response、provider/modelの識別情報、usage、finish reason、正規化されたエラーが含まれます。このAdapterが無効でもFactoryは動作しなければなりません。

## SourceControl

対応機能には、リポジトリの調査、branch/worktreeの作成、diffの取得、commitの作成、PRの作成などがあります。マージには別途権限が必要であり、既定では人の承認を必須とします。

## Execution

分離されたworkspaceを作成し、スコープを限定したリポジトリ／成果物をマウントし、許可リストにあるコマンドを実行します。出力を取得し、CPU／メモリ／時間／ネットワークの制限を適用し、workspaceを破棄してクリーンアップ結果を報告します。ホスト上での実行へ暗黙にフォールバックしてはいけません。

## Observability

構造化されたライフサイクルイベント、メトリクス、トレース、成果物への参照を受け取ります。Secretのマスキングは、永続化またはエクスポートの前に行います。

## 互換性

Adapterはセマンティックな契約バージョンを宣言します。Coreは互換性のないメジャーバージョンを拒否し、起動時に必要な機能を検証します。
