# 外部Issue参照とTask Source Adapter

FactoryはGitHub Issues等の依頼管理を置き換えない。独立したFactory Taskは削除済みで、依頼は外部Issue、実行の単位と証跡はRunとして扱う。

## 不変条件

- 外部Issueの識別子は `provider + instance + external_id`。異なる接続先を混同しない。
- 取得結果は同一の外部Issue参照へ冪等に保存する。別の独自タスクは作らない。
- Runごとに実行時の `issue_snapshot` を固定し、後のキャッシュ更新で過去要件を変えない。
- Issue本文とリポジトリ文書は信頼できない入力。取得・保存だけではAI実行や権限昇格を許可しない。

## 現在の契約と入口

`TaskSourceAdapter.fetch_issue(external_id) -> ExternalIssue` が読取境界。
`import_issue(factory, adapter, external_id)` は内部/Python APIとしてID整合性と保存を扱う。
保存は既存のFile/SQLite Adapterで行い、Task SourceはFactoryの保存先を直接操作しない。

通常の利用者は認証済みWebで登録RepositoryのIssueを選択し、明示同意して実行する。
手動取り込み・紐付けのWeb入口は削除済み。CLIは既存の`sf issue develop`を使う。
GitHubの読取・認証・ページングはAdapter/組立箇所に閉じ込め、初期ProviderはGitHubを正式採用する。

要件分割による子Issue作成・親子関連は既存の専用tracker契約と承認付きWorkflowで扱う。
読取だけのTask Sourceに書込能力を追加しない。バックグラウンドpollで開発を開始しない。

詳細: [外部Issueモデル](../external-issue-model.md)、[Web実行](../local-web-execution.md)。
