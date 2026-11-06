# ADR-0007: Harness Compositionは全候補の明示選択と単一Profileに限定する

- 状態: 採用（マージ後）。R05b、context構成の候補作成のみ。

複数の開発ルールを検出した時に、ファイル名や走査順から優先順位を推測しない。
対象scopeの全ルール候補を、順序付き採用か理由付き除外のどちらかへ明示する。
子scopeのルールを親/兄弟scopeへ広げず、Profileは1つだけ採用しcommandをmergeしない。

構文不正/読込失敗/不完全走査は除外して回避できない。例示Profileは採用不可。
複数候補の警告は明示選択で解決できるが、自然言語の意味の整合性保証ではない。
構成結果・順序・除外理由・inventoryと参照hashをbundle hashへ結合し承認の対象とする。

これはRepository内のcontext構成であり、Factory強制Policyの変更や実行権限の付与ではない。
実行前に最新の検証・構成結果と承認を照合する。Factory/Project/Task間の一般的な
設定merge、semantic conflict検出、command overrideは具体的な要件が出た後に別途設計する。
