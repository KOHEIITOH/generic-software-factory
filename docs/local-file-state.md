# ローカルでDBなしのTask保存を試す

初期StateStoreのFile Adapterと、Task保存用のCLIを追加しました。
**Taskの作成・取得・外部identityの重複取込みが対象です。Web/Run/承認/evidenceのFile移行はまだです。**
既存の`sf task`や`sf web`はSQLiteを使う従来動作を維持します。

## 試す

リポジトリ直下で、インストール済みの`.venv/bin/sf`を使います。
保存先の親ディレクトリは存在している必要があります。

```sh
.venv/bin/sf state --backend file --root /tmp/sf-file-check create "DBなしの確認"
```

返されたtask_idで読み込みます。別のコマンド起動でも同じ内容を取得できます。

```sh
.venv/bin/sf state --backend file --root /tmp/sf-file-check show <task_id>
```

外部Taskの取込みは次のとおりです。これは入力済みmetadataの保存確認で、ネットワークには接続しません。

```sh
.venv/bin/sf state --backend file --root /tmp/sf-file-check import \
  --provider github --instance sample/project --external-id 42 --prompt "保存確認"
```

同じコマンドを再実行すると同じtask_idが返り、Taskは増えません。
同じidentityでpromptを変えても元のTaskを保持します。identityは現在のSQLiteと同じく
provider/instance/external_idの完全一致で、勝手にcase変換やrepository名変更をしません。

保存物は`/tmp/sf-file-check/tasks-v1/<id>.json`です。SQLite接続は行わず、DBファイルも作りません。
`/tmp`は試験向けで、永続保存には自分で管理するlocal disk/volumeを明示してください。

SQLite Adapterも同じTask保存CLIで比較できます。保存先は分けてください。

```sh
.venv/bin/sf state --backend sqlite --root /tmp/sf-sqlite-check create "SQLiteの確認"
```

## 保証と制約

- Linux等のPOSIX、flock、descriptor-relative/no-follow操作、directory fsyncを備えるlocal filesystemが対象。
  WindowsやNFS/S3 mount等に同等の保証を約束しません。未対応なら起動拒否します。
- 協調するwriter間でprocess lockを取り、新規JSONを一時ファイルへ書き、file fsync、atomic replace、
  directory fsyncを行います。lock timeout時に無排他で書き込むfallbackはありません。
- external identityから安定したopaque IDを作り、同時取込みと再送を同じrecordへ集約します。
  hash衝突時は既存内容と照合して拒否し、別Taskを上書きしません。
- recordは最大1 MiB、schema/versionは1。Task/source/eventを同じrecordに保存し、重複JSON key・
  未知version・不正内容・symlinkを拒否します。自動修復やデータ削除はしません。
- 強制終了で残る未公開の.tmpはTaskとして扱いません。孤立tmpの自動回収は後続です。
  通常の例外時は一時ファイルを回収します。
- 初期操作はcreate/get/import-onceのみ。既存recordの更新/CASやRun・承認の原子操作は後続です。
- ファイルは0600で保存しますが、root/volumeの管理と読取権限は利用者の責任です。
  OS owner等の非協調的な変更まで防ぐ改変不能媒体ではありません。
- 書込後のfsync失敗では保存結果が不明な場合があります。成功とせず、import再試行は同じidentityで
  照合・durability確認します。通常createは別Taskを作る操作なので、応答喪失時に盲目的に繰り返さないでください。
- 既存factory.sqlite3のあるrootをFile用に指定すると拒否します。逆にFile用rootへSQLite Adapterや
  Factoryを起動することも拒否し、黙って別のDBを作りません。既存データの移行ではありません。
  export/importで既存IDを維持する移行はP05で実装します。

テストでは共通契約をFile/SQLiteへ適用し、SQLite接続禁止下のFile CLI、別プロセスの同時import、
lock timeout、破損/将来schema、symlink、file/directory sync・replace失敗を確認します。
これはDBなしで全WorkflowやIssue-to-PRが動いたという実証ではありません。
