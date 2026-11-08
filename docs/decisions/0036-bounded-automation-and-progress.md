# 0036: レビュー対応・Issue分割を有限の状態機械で進める

利用者の方針: 判断を質問で止めず、選択と根拠を証跡に残す。PR完了までの無限pollingはしない。
今回の実装を、永続予算→PR取得/CAS→修正controller→子Issue分割/順次実行→Harness共通層の
小さなPRに分ける。実AI/実サービスの最終通しは利用者PCで、CIでは外部サービスをfixtureにする。

## 有限実行の判断

- advanceは現在の外部状態を1回確認し、処理・待機・停止・完了のいずれかを保存して終了する。
- 既定は同じPR/作業単位の最大3回、モデル8呼出し、token予約300万、API2500回、書込128回、
  子Issue8件、期限7日。構成可能だがhard capを持ち、再起動やresumeで予算をリセットしない。
- tokenは最大出力と入力byte数、SDK再試行を含め保守的に予約する。料金保証ではない。
- 同一candidateの再生成、同じ指摘への重複対応、依存不成立、scope変更、結果不明は停止/待機として記録。
- 外部書込前にintentを保存する。失敗/timeout後は正確な外部照合なしに再送しない。
- 人間レビュー待ち/merge待ちはworkerを回し続けない。人間の承認を推測してmergeしない。

## 依頼とHarnessの判断

分割単位はGitHubの子Issueにする。ローカルPlan/DAGは実行状態であり、独立TaskのCRUDを復活させない。
各子Issueは変更範囲、受入条件、承認済み検証シナリオ、依存を持ち、件数・深さを制限する。
依存完了はIssueのclosedだけで判断せず、対応PRのmergeと成果物を照合する。

HarnessはFactoryの強制Policy、operator管理のProject共通、Repository内、directory scopeを組み合わせる。
Projectルールは同じ共通設定を複数repositoryから参照できるようにし、Runへ有効版を固定する。
自然言語のルールで権限・command・書込scopeを拡大させない。競合を暗黙に優先順位で解決しない。

## 最初の基盤

AutomationSessionは既存のFile lock/no-follow/fsync/atomic replaceを再利用する。専用DBは不要。
予約・結果・判断理由・予算を永続化し、欠落/破損/未知schemaを空状態に戻さない。
BudgetedModelはexact prompt/roleの結果を再利用し、結果不明の推論を再送しない。
HTTPとモデルはそれぞれのAdapterでtimeoutを持ち、session期限も各action前に確認する。
