# 0029: 複数ファイルの候補commitを公開操作から分離する

## 決定

既存SourceControlに互換なChangeSourceControl契約を追加し、GitHub Adapterの
prepare_commitでexact parent上の変更前blobとmodeを全件照合してからGit objectを作る。
GitHub固有のSHA1 blob identity、REST payload、認証はAdapter内に閉じる。

全変更のblob、既存base_treeを使ったtree、単一parentのcommitを作り、返されたblob SHAと
commitのtree/parentを確認する。新規ファイルの既存path・親file/submoduleとの衝突、
重複、truncated tree、不正scopeは書込開始前に拒否する。
この処理はbranchを移動せず、PRも作らない。複数fileを別々のcommitにしない。

## 制約と後続

Git objectのPOST全体はトランザクションではない。失敗時に未参照objectが残り得る。
自動再試行は行わず、例外を成功扱いしない。実配送controllerへ接続する前に、永続intent、
結果不明の照合、同一repo直列化、実証跡と配送承認の確認が必要。
既存のデモwrite_file経路は維持し、WebやCLIからこの処理を起動する入口は追加しない。

## 検証

API fixtureで複数fileのbytes/mode/parent固定、全前提の書込前検証、部分失敗での停止、
応答とcandidateの不一致、branch/PR APIを呼ばないことを検証する。
本物のGitHub配送・AI実装・Docker実通しの代替とはしない。
