# Policy Foundation（実験的）

Factoryの実行前に、権限と上限を明示的に判定するための小さな基盤です。

- `read-only` はデフォルト許可
- `workspace-write` と `external-action` はデフォルト拒否
- 管理者が許可した場合も、実行単位の明示的な承認が必要
- timeout と retry の上限を超えた要求は拒否

`ExecutionPolicy.evaluate(ExecutionRequest(...))` は `allow` / `require-approval` / `deny` と理由を返します。

現段階ではアプリケーション層の判定であり、OS sandbox・ネットワーク制限・ツール権限の強制・永続的な承認ワークフローは未実装です。権限を許可するだけで安全な実行環境が得られるわけではありません。既存の `dev-smoke` は独立したサンプル限定経路です。

次の段階でFactoryのRun起動時の判定・監査記録、Runtime capability宣言、承認の永続化、OS隔離へ接続します。
