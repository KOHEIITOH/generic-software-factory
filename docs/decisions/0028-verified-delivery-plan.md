# 0028: 検証対象と配送する変更を同じバイト列へ固定する

## 決定

配送前の純粋関数 `build_delivery_plan` を追加する。SourceSnapshotServiceから得た
manifestと全sourceファイルを照合し、ProposalScope/変更案の同一Run・revision・Harness・
source fingerprintを再検証する。変更対象以外の改ざんも拒否する。
既存ファイルの実行権限を維持し、新規ファイルには実行権限を付与しない。

配送先repository/base branch、元revision、変更前後のSHA256、権限をplan fingerprintへ
含める。同一planには同じbranch名とPR照合markerを割り当てる。
CoreはGitHub APIやGit blobのハッシュ方式へ依存しない。

## 境界と未完了部分

このplanはチェック成功・独立レビュー・配送承認を証明しない。snapshot descriptor自体も
呼び出し元が信頼された保存先から取得する必要がある。公開APIやWeb実行は追加しない。
将来の配送controllerは信頼されたcollectorの証跡と同一planへの承認を確認してから、
Adapterでcommit・branch・Draft PRを作る。結果不明時は永続intentと実サービスを照合し、
盲目的に再送しない。これらは別の小さなPRで実装する。

## 検証

全inventoryの改ざん・欠落・重複、不正mode/サイズ、別Run/revision/Harness、
配送先の差異、変更前後bytesと実行権限の識別、host副作用がないことを単体テストする。
実GitHubへの変更配送や実Issue-to-PRの成功を意味しない。
