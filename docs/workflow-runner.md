# Provider-neutral Workflow Runner (MVP)

`run_workflow` は、`WorkflowDefinition` と既存の `AgentRuntime` 契約を接続する最小の実行オーケストレータです。

- Runtimeは `runtime_for(step_id)` から注入し、CoreはCodex/Copilot等を直接importしない
- StepごとのPromptも `prompt_for(step_id)` から渡す
- DAG依存関係とPolicyを事前評価し、成功したStepのみ完了扱いにする
- Runtime失敗・Policy拒否・例外で停止し、結果を呼び出し元へ返す
- **初期実装ではREAD_ONLYのみ実行**。承認済みの書き込みもこのRunnerでは実行しない

## 未対応

これは実行基盤の最小縦断スライスであり、まだCLIやFactoryのSQLite永続化には接続していません。Quality Gate、改善ループ、再開、並列実行、実行履歴のDB保存、OSレベル隔離、Agent Runtimeの権限制御の強制は後続PRで扱います。

特にアプリケーション側のREAD_ONLY宣言だけでは、実際のRuntimeがファイルを変更しないことを保証できません。信頼できる隔離実行環境が必要です。
