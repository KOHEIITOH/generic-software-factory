# Quality Gate 基盤（PR #16）

品質判定をFactory Coreに固定の言語・CI・モデルを埋め込まずに行うための、宣言的な評価基盤です。

- `QualityGate(id, required)`：利用者が必要なチェックを定義
- `QualityEvidence(check_id, passed, detail, source)`：外部の検証器・CI・テストAdapterが生成する証拠
- `evaluate_quality(gates, evidence)`：チェックIDで照合し、必要な証拠がなければ失敗として扱う
- `QualityReport.feedback`：失敗・未提出の証拠を次の改善試行へ渡すための文字列

特定の言語、テストコマンド、GitHub Actions、AIプロバイダに依存しません。

## セキュリティ境界と未実装事項

本モジュールは証拠を**評価するだけ**で、テストの実行や証拠の真正性検証は行いません。AIが提出した `passed=True` をそのまま信頼する運用は不可です。独立した検証Adapterと隔離環境が必要です。

Quality GateをWorkflow RunnerやImprovement Loopへ接続し、検証結果の永続化・証拠の信頼性・実行環境の隔離を実装するのは後続PRの対象です。
