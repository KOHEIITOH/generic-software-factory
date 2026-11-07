# 0035: 独立Taskを削除し、外部Issue参照へ直接関連付ける

## 決定と背景

既存データ/旧APIの互換性より、独立Task管理を削除して実行フローを単純化することが
利用者から明示承認された。互換layerやTaskデータの移行を実装上の前提にしない。

`IssueReference(provider, instance, external_id)`から索引を導出し、IssueSnapshotは外部サービスの
読取キャッシュとしてのみ保存する。単独Taskの作成メソッド、TaskRecord、Task table、
TaskSource mapping table、Task専用Project関連付け、旧Task API/CLIを削除する。
共通の外部取得契約`TaskSourceAdapter`は再利用し、GitHub以外の実装を追加しない。

Run、Harness承認、Project/Repository、実行権限、監査、usageの参照をissue_keyへ置換する。
Runには実行に使うIssue snapshotを固定し、実際のRuntime入力と一致させる。
上流Issueの再取得はcacheだけを更新し、過去Runを編集しない。

旧Taskデータのあるrootを検出したら停止する。削除・変換・別namespaceへの暗黙fallbackは
しない。新しい空のrootでIssueを取り込み直す。配送結果不明の旧Runについては外部状態の
照合が必要であり、root切替は無条件な再配送許可にならない。

## 汎用性と安全境界

CoreにはIssue参照と既存Adapter契約だけを置き、GitHub固有API/認証を追加しない。
DBは任意のまま、Fileはissues-v2/dashboard-v2、SQLiteはissuesを使う。
旧Task形式や不明schemaをIssueとみなして読み替えない。
承認のscope、Run完了CAS、source/品質証跡、配送intentと復旧の検証は維持する。

## 検証

File/SQLiteで同じ外部参照・cache更新・Run要件固定を検証する。
旧Task CRUD/CLI/APIなし、Task tableなし、旧形式・別Issue・破損の拒否、並行更新、
再起動、承認、証跡、Issue→PRフローの回帰を確認する。
Web buildと実ブラウザでIssue一覧/新preflight route/旧Task入口なしを確認する。
実Dockerの縦断試験をCIで再実行する。実Bedrock/GitHubの最終試験は引き続き利用者PCが対象。
