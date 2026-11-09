# WebとIssue/Runのローカル保存

```sh
uv run sf web --rebuild
```

Webの閲覧とIssue/Runの証跡保存にDBサーバーは不要。通常のWeb実行は登録設定からIssueを選択し、実行時に要件を取得・固定する。手動取り込みは削除済み。閲覧にはDocker不要だが、開発実行には必要。
独立Task・旧Task CLIは削除済み。依頼の本文は外部Issueで管理する。

## 保存先とbackend

`SF_DATA_DIR`で保存先を指定する。対応するPOSIX環境の新しい保存先はFileを選び、
SQLiteを開かずにIssue参照・観測キャッシュ・Run・Project/Repository・承認・証跡を保存する。
新しいIssue形式のSQLiteがある場合はSQLiteを選ぶ。`SF_STATE_BACKEND`でも明示できる。
非POSIXではSQLiteを選ぶが、ローカル開発実行の隔離・journalは別途POSIX要件を持つ。

旧Task形式はサポートしない。移行・互換layer・自動削除は行わず、新しい空の保存先を使う。

```sh
SF_DATA_DIR="$HOME/.sf-factory-issues" uv run sf web --rebuild
```

CLI operator設定のdata_rootも同じ絶対pathにする。
詳しくは[外部Issueモデルと互換性](external-issue-model.md)を参照。

## Fileの保存境界

Issueキャッシュは`issues-v2/<issue_key>.json`、関連付け・Run・承認・証跡は
`dashboard-v2/state.json`（schema 5）。Issue identityはprovider/instance/external_idから導出し、
同じIssueの再取得はキャッシュだけを更新する。Runには実行時の要件を固定保存する。

既存のPOSIX process lock、no-follow、サイズ制限、private file、fsyncとatomic replaceを使う。
不明なschema、欠落、破損、fsyncの結果不明は空状態へ戻さず停止する。
同一保存先の別process更新もロックする。ネットワーク共有・S3・分散worker向けの保証ではない。
SQLite/Fileを同じrootへ混在させず、暗黙に切り替えたり移行したりしない。

Harness承認・prepared Runは同一保存境界で原子的に処理する。
source snapshot・品質/レビュー証跡・配送intentの安全条件は維持する。

## 確認

FileモードでSQLite接続を禁止したテスト、別processの競合、replace/fsync失敗、
旧形式拒否、Issue参照の安定性、過去Runの要件固定を検証する。
[PCのIssue実行手順](local-issue-development.md)も参照。
