# Bounded Improvement Loop（実験的）

`run_improvement_loop(execute, evaluate, ...)` は、試行・品質評価・フィードバック・再試行を制御する小さな実行基盤です。

- `execute(attempt_number, previous_feedback)` で候補を生成
- `evaluate(output)` で品質基準を評価し、合否と次回へのフィードバックを返す
- 成功、試行上限、時間上限、Policy拒否、例外で停止
- 各試行の番号・合否・フィードバックを結果に記録
- 書き込み・外部操作はPolicyでデフォルト拒否、明示的な許可と承認が必要

**重要な制限**：これは実行制御の部品であり、AIモデルやGitHub、shell、Dockerを自動実行するものではありません。時間上限は協調的な判定で、実行中のcallbackを強制終了しません。callback自身でtimeoutと隔離を実装する必要があります。実行履歴のDB永続化、外部コスト予算、承認の永続化、Quality Gateの独立検証は後続課題です。
