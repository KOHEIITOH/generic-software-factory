# Flexible Workflow Foundation

Workflowを固定の「要件定義→設計→実装→テスト」に限定しないための、宣言的なDAG（有向非巡回グラフ）定義と事前評価の基盤です。

- `WorkflowDefinition` に任意のStepを列挙し、`depends_on` で依存関係を定義する
- 「実装から開始」「調査から開始」など、入口を固定しない
- 依存が満たされた複数Stepを同時にreadyにできる
- 重複ID、未知の依存、自己依存、循環依存は拒否
- Stepごとに `Capability` を宣言し、Policyで実行可否と承認待ちを評価する

`evaluate_workflow` は **pureな事前評価** で、AIやコマンドの実行、状態永続化、再試行、並列スケジューリングを行いません。

実際のWorkflow実行エンジン、承認の永続化、監査ログ、Quality Gate、再開・キャンセルは後続の実装対象です。アプリケーションPolicyはOS隔離を保証しません。
