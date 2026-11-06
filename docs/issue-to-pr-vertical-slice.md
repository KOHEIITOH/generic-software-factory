# Issueを依頼、Runを実行履歴にする縦断実装

## 完成の定義

実際のGitHub Issueから、承認済み要件/source/Harnessを使ってAIが変更し、隔離環境で実際の
テストと品質検証を行い、独立したレビューを経て、その変更に対応するDraft PRを作れること。
fixtureやmockだけの成功、デモmarker PR、事前チェック、読み取り専用Runを完成とは呼ばない。

## 利用者のモデル

- Issue: 開発依頼と更新元。別のTaskタイトル/本文を編集して二重管理しない。
- Run: 同じIssueについての一回の試行。承認、入力snapshot、ログ、検証結果とPR参照を紐付ける。
- 内部Task: 互換性のために残す外部Issue identityへの参照と取込時の要件snapshot。
  既存Task/Run/承認のIDやデータを削除しない。新しいRunは実行承認時の要件を別途固定する必要がある。

## 段階と確認条件

| 段階 | 完了条件 | 現状 |
| --- | --- | --- |
| Issue中心の閲覧 | 既存Issue identityのまま複数Runを表示。独立Task作成を主画面から外し、旧API/データを維持 | PR #101で実装済み |
| 安全な実行入力 | source、変更案、承認済みcommandを検証済み実行器へ渡せる。host実行へfallbackしない | PR #102でbounded stdinを接続。候補sourceの隔離内materialization/check接続を追加、実Docker CIで検証 |
| AI実装 | 推論/Runtimeを安全な境界で接続し、実要件から変更を生成する。credentialをWorkerへ漏らさない | scope固定の変更案データ検証を追加。実provider/承認/実行への接続は未完了 |
| 実チェック・レビュー | 実際のartifact/revision/diffとcollectorを証跡へ固定する | 候補commandの隔離実行を追加。実test-count collector/独立reviewの接続は未完了 |
| 実変更の配送 | 検証済みの同一変更を承認範囲内でDraft PRへ届け、結果不明時を照合する | デモ経路のみ |
| Webから実行 | operator認証、明示承認、同一repo直列、永続状態、再起動時の安全停止を備える | 未接続 |
| 実通し試験 | 試験用Issue等からAI実装・実テスト・レビュー・Draft PRを実サービスで確認 | 未完了 |

## 最初の閲覧変更

`GET /api/issues`は保存済みの外部Issue参照とIssueごとの直近10 Run、全Run数を返す。
ローカルTaskはこの一覧に混ぜず、既存`/api/tasks`・`/api/runs`やCLIでは保持する。
Issue一覧のlimitは外部Issueを選んだ後に適用し、ローカルTaskに押し出されないようにする。
過去のread-only/Harness準備Runも履歴に含むため、status=successだけでは実装・配送完了と表示しない。

## 環境依存と安全条件

既存の隔離器は実際のcgroup v2 CPU/memory/PID制限を要求する。Dockerが存在するだけでは
実行可能としない。AI CLIのlogin表示も実際の推論成功を証明しない。
実行器または認証が未対応の場合、できたように表示せず、実通し試験を未完了として扱う。
AWS作成・デプロイ・有料Bedrock呼出しは従来どおり別の承認対象。
