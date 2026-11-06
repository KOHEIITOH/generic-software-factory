# ADR-0006: Harness承認は対象版に固定した一回限りの記録とする

- 状態: 採用（マージ後）。R05a、ローカル永続化のみ。

Harnessの検出・検証結果を人間の承認と混同しない。既存ExecutionGrantのbooleanを
直接永続化して実行権限へ昇格させず、Harness適用に限定した承認記録を独立させる。

検証問題のない空でないinventoryから、候補のpath/scope/kind/hashとProfile参照hashを
正規化してbundle hashを算出する。未解決の複数ルールや不完全な検出結果を承認対象にしない。
Compositionは別工程であり、ここで規約の優先順位を推測しない。

承認対象はProject ID、Repository ID、Task ID、exact revision、bundle hash、
operation=apply_harnessに固定する。期限は24時間以内、明示した承認者と判断を保存する。
SQLite transactionで一回だけconsumeし、同時実行・再利用・期限切れ・失効・対象変更を拒否する。
consumeに失敗した処理は適用へ進まない。失効/判断/消費の成功イベントを同じDBへ保存する。
失効は既に実行中のRunを止める機能ではなく、cancelとの連携が別途必要である。

これは認証機能ではない。record/revoke/consumeを呼べるのは信頼された制御側のみとし、
reviewer文字列は認証・権限検査後のidentityを渡す。Repository内容やHTTP payloadが
reviewerを名乗って承認できる入口は作らない。DBはRepository/snapshotから分離して管理する。

適用前に制御側が現在のrevisionとHarnessを再検証し、新しいbundle hashでconsumeする。
旧hashをそのまま渡して変更を見落とす呼出しは不可。消費後に失敗した場合は安全側で再承認とし、
勝手に承認を再有効化しない。Runとの原子的な接続と復旧はR06以降の課題とする。

この承認だけでは実装・push・PR・Merge・Deployを許可しない。本人性・ロール・組織認可・
Web/API操作・OS隔離・公開鍵署名・改ざん耐性のある監査基盤は本PRの対象外。
既存のImplementationPlan.readyはfalseのまま維持する。
