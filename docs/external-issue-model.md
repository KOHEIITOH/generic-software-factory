# 外部Issueを依頼、Runを実行単位にする

Factory独自のTaskは廃止した。単独Taskの作成・編集・保存・API・CLIは存在しない。
開発依頼はTaskSource Adapterが取得する外部Issueで管理し、Factoryは実行と証跡を管理する。
GitHubが初期標準だが、共通契約にGitHub API型・認証・番号の解釈を持ち込まない。

## 共通参照とキャッシュ

`IssueReference(provider, instance, external_id)`が外部サービス上の依頼を識別する。
`issue_key`はこの3項目のcanonical JSONから導出するSHA256索引で、Factory独自のTask IDではない。
異なるprovider/repository/番号を区別し、File/SQLiteが同じ参照を返す。

`IssueSnapshot`はその参照・取得した本文・URL・観測時刻の読取キャッシュ。
同じIssueを再取得すると最新内容へ更新するが、Factory内で独立した依頼を作成する機能はない。
外部Issueを取得するAdapterは既存`TaskSourceAdapter`契約を使う。

## Run・承認・証跡

Run、Harness承認、Project/Repository関連付け、監査、usage、実行権限は`issue_key`で関連付く。
各Runは実行に使った`issue_snapshot`を別途固定する。キャッシュ再取得後も過去Runの要件は変わらない。
実行時には保存したものと同じ要件をRuntimeへ渡す。品質証跡・source snapshot・配送intentは
引き続きRunのrevision・Harness・変更hashへ固定する。Issue参照の変更は別の承認範囲となる。

## 削除した入口と形式

- `sf task ...`と旧`sf state ...`の作成/previewコマンド。
- `/api/tasks`一覧・作成・repository紐付け・preflight。
- Factoryの`create_task`等、TaskRecord、Task専用tableとTaskProject関連付け。

Webは`GET /api/issues`、`POST /api/issues/{issue_key}/repository`、
`GET /api/issues/{issue_key}/implementation-preflight`を使う。
Issueの取得はGitHub import、開発実行は`sf issue develop`を使う。

## 互換性

この変更は破壊的変更で、旧Taskデータの移行や互換aliasは提供しない。
旧`tasks-v1`/`dashboard-v1`、Task tableを持つSQLiteを検出すると停止し、自動削除・変換しない。
旧保存先がある場合は新しい空の保存先を指定してIssueを取り込み直す。

```sh
SF_DATA_DIR="$HOME/.sf-factory-issues" uv run sf web --rebuild
```

CLIのoperator設定の`data_root`も同じ新しい絶対pathへ変更する。
旧Runのresume・承認は新形式に引き継がない。旧配送結果が不明な場合は、GitHub側を照合してから
新しいRunを開始する。保存先変更を配送の無条件な再送許可として扱わない。

新しいFile形式は`issues-v2/<issue_key>.json`と`dashboard-v2/state.json`（schema 5）。
SQLiteは`issues`を参照元にし、Task tableや別のtask_sources tableを作らない。
DB不要で動く方針は維持する。
