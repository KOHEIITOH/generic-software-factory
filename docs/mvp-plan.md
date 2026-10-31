# MVP計画 — v0.1

## 目標

利用者が任意の対応Agent Runtimeと対象リポジトリを設定し、範囲を限定したタスクを1つ投入して、Factory Coreを変更することなく、テスト済みのPull Requestを受け取れることを実証します。

## MVP Workflow

`Task → Validate → Plan → Human plan approval → Implement → Test → Review → PR creation → Human merge approval`

## マイルストーン

### M0 — 仕様と契約

- Coreの用語と境界を確定する。
- 設定スキーマとAdapter契約を定義する。
- Workflowの状態機械とイベント形式を定義する。
- セキュリティ基準を文書化する。

### M1 — 最小の垂直スライス

- CLIを実装する: `init`、`validate`、`doctor`、`run`、`status`、`cancel`。
- 1つのAgentRuntime Adapterと1つのSourceControl Adapterをリファレンス実装としてサポートする。
- 1つの分離実行用Execution Adapterをサポートする。
- タスク入力からPR作成までのWorkflowを1つ実行する。
- Runtime／Provider／プロジェクトの選択は設定可能に保ち、Coreにハードコードしない。

### M2 — 信頼性

- 再試行、タイムアウト、キャンセル、中断からの再開を追加する。
- 監査ログと成果物マニフェストを追加する。
- 決定的なQuality Gateと失敗の証拠を追加する。
- 権限テストとSecretのマスキングを追加する。

### M3 — 置き換え可能性の実証

- 2つ目のAgentRuntime Adapter、または契約テスト済みのMockを追加する。
- Runtimeを切り替える際に必要なのが設定／Adapterの変更だけで、Coreの変更が不要であることを実証する。
- Adapterの適合性テストを追加する。

## 受け入れ条件

1. 手順書に従い、クリーンなcheckoutを初期化できる。
2. `validate`が、実行前に設定の不足や不正を検出する。
3. `doctor`がAdapterへの接続と必要な機能を確認する。
4. 範囲を限定したタスクを分離workspaceで実行する。
5. 各runについてAgent Roleの指示とHarnessのバージョンを記録する。
6. test/lint/securityのGateが機械可読な証拠を生成する。
7. 失敗、タイムアウト、キャンセル、再試行の状態を記録する。
8. PRを作成できる。マージと本番デプロイは引き続き承認を必須とする。
9. Secretがログ、prompt、成果物、commit済みファイルに現れない。
10. AgentRuntime Adapterの置き換えにFactory Coreの変更が不要である。

## 対象外

自律的なマージ／デプロイ、Core Policyの動的な自己編集、終わりのないAgentループ、複数リポジトリのオーケストレーション、汎用ダッシュボード。

## 実装前の未決事項

実装言語と配布方式、最初のリファレンスAgentRuntime、最初のSourceControl Provider、実行バックエンド、状態ストア、Workflow定義形式、ライセンス、リポジトリの公開範囲。
