# 承認済みソースsnapshot（R04c）

`SourceSnapshotService.create(run_id, root=...)` はprepared Runに固定したcommitから、
通常のGit blobだけをFactoryの非公開領域へ保存します。作業ツリーの現在内容は使わず、
未追跡/ignoredファイル、Git metadata、認証設定を丸ごとコピーしません。
対象は登録済みlocal-git Repositoryと一致するrootのみです。

ローカルのrev-parse/ls-tree/cat-fileを使い、hooks、filters、置換ref、遅延fetchを使いません。
Git通信protocolをこの読込プロセスだけで無効化し、資格情報の問い合わせも行いません。
symlink/submodule/特殊mode、絶対/親参照、機密名、.git/.sf-factoryのpathは拒否します。
機密名の検査は内容のSecret検出ではありません。外部AIへの送信前には導入先Policyの確認が必要です。

上限は1,000ファイル、1ファイル1 MiB、総16 MiB、path深さ16、Git読込全体30秒です。
UTF-8 pathを要求し、blob内容はbinaryも保存できます。Git treeとmanifestは各1 MiBまでです。
承認した選択済みHarnessとProfile参照のhashがcommit内のblobと一致しなければ拒否します。

保存先は `Factory.root/source-snapshots/<uuid>/payload/`。ファイルはhost上では0600にし、
元のGit modeはmetadataへ保存します。sourceをhostで実行しません。manifestはRun/commit/
Harness/path/mode/サイズ/内容SHA-256に結合し、そのfingerprintをFactory DBへ保存します。
Runはpreparedのままです。

`verify(run_id)` は保存したmanifestと各blobを再検査し、改変・不足・余分なファイル・symlinkを
拒否します。descriptor-relativeな読込とO_NOFOLLOWを使います。これはownerが変更できない
物理的immutable storageではなく、信頼されたhost領域の改変検出付きartifactです。
同じRunのsnapshotを上書きせず、再利用はverifyしてから行います。

ステージングとDB transactionを使い、通常の保存失敗時は自身の生成物を除去します。
host強制停止時のorphan artifact回収は後続です。snapshotが検証できても実行許可にはなりません。
実行先への転送・検証、AIが提案する変更の受入れ、結果差分・テスト・レビュー・Draft PRへの接続は
次工程です。現在のIssue-to-PRの通し実証は未完成です。
