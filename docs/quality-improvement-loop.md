# Quality Gate × Improvement Loop 統合

`run_quality_improvement_loop(execute, collect_evidence, gates=...)` は、AIやCI製品に依存せずに以下を接続します。

1. Policyと試行回数・時間制限を確認
2. 注入された実行Adapterが結果を返す
3. 独立した証拠収集Adapterが品質検証結果を返す
4. 必須Gateの証拠が欠けるか失敗したら、理由を次の試行へ渡す
5. Gate合格・試行上限・時間切れ・Policy拒否・例外で停止

このモジュール自体はAI呼び出し、テストコマンド、CI API、ネットワークを実行しません。証拠の真正性を検証する仕組みもありません。実際の運用では信頼できる独立した検証器と隔離実行環境が必要です。

既存のImprovement Loopと同じく、タイムアウトは協調的な検査です。実行Adapter自身に強制的な時間制限が必要です。
