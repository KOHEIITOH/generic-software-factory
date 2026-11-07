# 0031: branch/PRの結果不明を正確な外部状態で照合する

## 決定

ChangeSourceControlにbranchの有無/正確なcommit照合とDraft PR照合を追加する。
GitHub固有API/404/認証/PR payloadは既存Adapterへ閉じる。
既存branchが同じcommitなら再作成せず、異なるcommitなら停止する。force updateはしない。
branch作成後はref/type/commitを再読込し、失敗・不確定時は再試行しない。

Draft PR照合はstate=allとheadで検索し、repository、head/base ref、head SHA、draft/open、
markerとURL/番号をすべて照合する。base変更を隠さないため検索のbaseフィルタは付けない。
複数候補、closed/merged/ready、別SHA/marker/repository、未知/上限/ページング応答を拒否する。
これは読取だけで、照合失敗を新しいPR作成の許可にしない。

## controllerへの要件

branch_pending/pr_pendingの復旧は読取照合だけを行い、一致したreceiptだけを保存する。
対象が見つからない場合も、前の書込が未反映かもしれないため自動再送しない。
外部書込前の永続intentと実証跡・承認確認は別途必要。
このPR単体では新しいWeb入口や自動配送を有効にしない。

## 検証

REST fixtureで404→作成→再読込、同一branch再利用、異なるcommitでの停止、
timeout/未反映時の再送なし、正確なDraft PR照合、変更/閉鎖/曖昧/ページングでの停止を確認。
