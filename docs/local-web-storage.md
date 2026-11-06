# 一コマンドで起動するWebと保存先

通常の起動手順は変更ありません。

```sh
uv run sf web --rebuild
```

起動後に `http://127.0.0.1:8000` を開きます。TaskやProjectを登録すると保存され、
サーバーを終了して同じコマンドで再起動しても一覧から確認できます。
`sf state ...` の事前実行、DBサーバーの起動、Dockerは必要ありません。

## 保存先の選択

既定の保存先は、起動したディレクトリの `.sf-factory` です。起動ログに保存方式とパスを表示します。

| 保存先の状態 | 自動選択 |
| --- | --- |
| 新しい保存先、対応するPOSIXローカル環境 | File。SQLite接続・DBファイル作成なし |
| 既存の `factory.sqlite3` がある | SQLite。既存Task/Run/Project/承認を保持 |
| 既存のFileデータがある | File。先行する `sf state` のTaskも一覧に表示 |
| 新しい保存先、Windowsなど非POSIX環境 | SQLite。Fileの対応環境ではないため |
| 両方式のデータが混在する | エラー。片方を無視して空の状態では起動しない |

**既存のSQLiteを自動でFileへ移行する変更ではありません。** バックアップや承認・証跡も含む
移行検証なしに既存データの移動・削除は行いません。

任意の設定は `SF_DATA_DIR`（保存ディレクトリ）と `SF_STATE_BACKEND`（`auto` / `file` / `sqlite`）です。
通常は設定不要です。既存SQLiteを保ったままFile動作を試す場合だけ、別の保存先を指定できます。
例えばPOSIX shellでは次のように起動します（保存先の親は既存ディレクトリにしてください）。

```sh
SF_DATA_DIR=.sf-factory-file uv run sf web --rebuild
```

CLIの `sf task` / `sf run show` もWebと同じ選択規則・設定を使います。
保存方式を明示しても、異なる形式の既存保存先は上書き・移行しません。

## Fileで使える範囲

- WebのTask作成・一覧、GitHub Issue取込、検証済みリポジトリへの関連付け、実装preflight。
- WebのProject/Repository登録・一覧・重複検出。
- CLIで明示的に開始した既存read-only RuntimeのRun結果と監査イベント、WebのRun一覧。
  Runtimeの認証・利用料金は別の要件であり、Web起動やTask作成だけではAIを呼び出しません。
- プロセスを跨ぐ再読込、同一hostの協調するWriter間のロック。

信頼されたローカルcontroller向けには、Harness承認の記録・取消・一回消費と、
承認消費/prepared Run/manifest/auditの原子的保存もFile対応です。
Task/Project関連付けと登録リポジトリの照合を同じ保存境界で行います。
Webに承認・実行の入口は追加していません。

承認済みcommitのsource snapshotもFile対応です。payloadを先に永続化し、Runとの参照と監査を
同じ状態更新で登録します。参照登録が不明な場合はpayloadを保全して照合し、使用前には内容hashを再検証します。

品質・レビュー証跡もFile対応です。固定したcheck plan、対象revision/bundle/diff、収集者、
上限3回の試行に結びつけて記録し、最新の同じ試行だけで評価します。0件・不明件数のテスト、
失敗・省略・不完全レビュー、must-fixが残るレビューは合格にしません。証跡と監査の更新は同じ
document内で原子的に処理します。SQLite/Fileで同じ判定ルールを使います。

これらのAPIは信頼されたcontroller向けで、収集者の認証・実チェックの実行・artifact照合を
自動で行うものではありません。`eligible_for_delivery` は引き続き常にfalseです。
Issueから自動実装してDraft PRを提出する完成状態を意味しません。
WebにAgent起動や承認のHTTP入口を追加していません。

## 永続化と失敗時の動作

Task本体は `tasks-v1/<id>.json`、Web登録・関連付け・Runとイベントは
`dashboard-v1/state.json` に保存します。後者はschemaと単調増加versionを持つ16 MiB上限の
ローカル用documentです。大規模・分散運転用ではありません。

schema 1/2/3の既存File documentは、内容を検証してから同じID/既存データを保ってschema 4へ
原子的に更新します。既存Harness/snapshot状態は維持し、新しいevidence collectionを空で追加します。
旧バージョンのアプリは新schemaを拒否するため、更新後に古いアプリへ戻す場合はWriter停止と更新前バックアップの確認が必要です。
SQLからFileへの移行とは別のローカルschema更新です。

同一documentの変更は、プロセスロック、0600の一時ファイル、file fsync、atomic replace、
directory fsyncの順で保存します。Run状態と対応イベント、Repository登録と重複検出は同じ
ロック・documentの範囲で処理します。新しい保存先の方式選択もロックし、異なるbackendの
同時初期化を拒否します。旧来の `Factory` / 個別Storeを直接生成する呼出元とは保存先を混在させないでください。

- FileはPOSIX flock / O_NOFOLLOW / directory fsyncを備えるローカルfilesystemが対象。
  NFS、S3 mount、分散host間の排他やfencingは未対応です。
- 未知のschema、破損、初期化済みdirectory内のdocument消失、symlinkを検出すると停止。
  APIは503を返し、空の状態へ戻しません。新規初期化中の異常終了でも、不完全なdirectoryは
  自動で作り直さず、バックアップとログを確認してください。
- fsync失敗で公開結果が不明な場合は成功と返しません。Task/Project作成の応答を失った場合は、
  一覧で照合してから再操作してください。外部Issueの同じidentityは再取込しても同じTaskです。
- 強制終了前にRunが `running` と保存されていれば、そのまま残します。
  自動再実行や成功への書換えは行わず、新しいRun開始を拒否します。
  Workerの生存照合・明示的な復旧操作は後続で実装します。保存先を消して再実行しないでください。
- `*.tmp` が強制終了で残っても正式な状態には読み込みません。自動GCは後続です。
- バックアップはWriterを停止した上で保存先全体を取得してください。任意の一部ファイルを
  削除した際の整合性や、OS ownerによる非協調的な改変への耐性は保証しません。

## 検証

SQLite接続を禁止したWeb/CLI試験、別プロセスの同時更新、異なるbackendの同時初期化、
replace直前のプロセス強制終了、破損・消失・symlink・容量超過、Run timeout/例外結果、
SQLite既存データの互換試験を実施します。
実際の `uv run sf web --rebuild` でもHTML配信・Task作成/再取得とDBファイル0件を確認します。

### Snapshotの中断と照合

payloadのファイル/ディレクトリをfsyncし、未使用のUUID directoryをmkdirで確保してから配置し、
親directoryもfsyncした後に状態へ登録します。既存directoryは空でも置換しません。
参照登録に失敗した場合、正式な状態の読取で未参照と確認できた自分のpayloadだけを削除します。
結果不明や状態が読めない場合は削除せず失敗を返します。登録済みpayloadは後続のverifyで照合できます。
プロセス強制終了で未参照payloadが残る可能性があり、自動GC・一般的な復旧操作は後続です。
