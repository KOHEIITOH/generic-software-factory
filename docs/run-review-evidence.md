# Runへ固定する独立レビュー結果（R10a）

`RunEvidenceService.register_review` はチェック計画のあるprepared Runへ、実装者と異なる
reviewer identityと対象変更pathを固定します。record_reviewは認証済み制御側が確認した
producerからの結果だけを取り込み、Run/commit/Harness/差分/最新チェック試行へ照合します。
同じ試行の記録は上書きせず、新しい試行に古いレビューを再利用しません。

identityが異なる文字列だから独立レビューが成立するわけではありません。
controllerが実際のRuntime/session・本人性・権限を確認することが前提です。
このPRはAIレビュー呼出しやGitHubコメント取込みを実装しません。

## 応答契約

最大64 KiBのJSONで、schema_version=1、run_id、revision、bundle_hash、diff_sha256、
status（completed/failed）、complete、truncated、reviewed_paths、findingsを必須とします。
未知/重複フィールドを拒否し、モデルが自己申告するmust_fix_countも受け付けません。
findingsは最大100件でseverity（must-fix/should/nit）、path、正のline、summary、evidence。
must-fixの根拠は必須です。未知のseverityを捨てて指摘0件とすることはありません。

記録するのは応答hash・件数・状態のみです。指摘本文、ソース、promptはDBへ保存しません。
応答全文のArtifact保管は後続です。

## 集約と表示

同じ最新試行の全必須チェックが通り、レビュー処理が完了し、全対象pathを確認し、
切り詰めなしでmust-fixが0件の時にのみevidence_complete=trueを返します。
failed/不正JSON/未知severity/対象不一致/一部未確認を成功へ読み替えません。

```sh
.venv/bin/sf run evidence <run-id> \
  --revision <検査対象commit> \
  --bundle-hash <承認済み構成hash> \
  --diff-sha256 <検査対象差分hash>
```

0=保存した証拠が揃っている、1=不足/不合格、2=入力/対象不一致です。
CLIのexit=0はMerge/PR作成の許可ではありません。対象版は呼出元が現在の成果物から確認します。
この段階ではeligible_for_deliveryは常にfalseで、Runを実行完了へ遷移させません。

実モデルへの接続、report真正性の検証、source snapshotと差分の実生成、認証、隔離実行、
指摘修正、Draft PR提出は後続です。構造が正しいAIの回答でも、内容の正しさは別途検証が必要です。
