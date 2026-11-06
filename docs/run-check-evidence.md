# Runに固定するチェック証拠（R09a）

`RunEvidenceService` は既存Factoryのprepared Runへ、必須チェック計画と観測結果を保存します。
コマンド実行器ではなく、認証済み制御側・信頼された結果収集器向けの記録サービスです。
Web/CLIから任意の「成功」申告を取り込む入口は追加しません。

計画は対象commit、承認済みHarnessのbundle hash、差分SHA-256、必須check ID/kind、
collector identity、最大試行数（1〜3）に固定します。test種別は最低1つ必要です。
既存manifestのbundleと一致しなければ登録できません。計画や既存結果は上書きできません。

収集器は実行したreportのSHA-256、終了状態/コード、test件数を渡します。
command完了かつexit=0、testsは実行件数が正の場合のみ、既存Quality Gateの証拠へ変換します。
未実行/失敗/エラー/0件/件数不明は合格にせず、元の状態を診断へ残します。
Run/commit/Harness/差分/collectorの不一致、未計画チェック、古い試行の遅延callback、
上限超過は拒否します。最新試行に全必須結果が揃うまで、旧試行の成功を流用しません。
終端Runへの追加と旧成功の再評価も拒否します。

評価時にも現在の対象commit/Harness/差分を明示し、一致しない旧評価を返さないようにします。
チェック計画・結果・監査イベントは同じFactory DBへ保存し、トランザクションで整合させます。
stdout/stderrやファイル内容は保存せず、report hashを保存します。

## 信頼境界と残る接続

- controllerが実装結果のcommit/差分とcollectorの本人性・権限・report真正性を検証する。
  文字列のidentity/hashやcountを、外部呼出元が自己申告しただけでは証拠にならない。
- 元の承認base commitと、実装後の検査対象commitの祖先関係は本サービスでは検証しない。
  snapshot/実行器からの信頼された受渡しが後続で必要。
- report本文/成果物の保存・取得、実チェック実行、試行の強制停止は後続。
- `checks_passed`はチェック集約だけ。独立レビューはまだmissingで、
  `eligible_for_delivery`は常にfalse。Run状態を合格や実行完了へ更新しない。
- 実Gitで準備したRunと同じcommit内の同梱calculator fixtureを実unittestで実行し、
  意図的な未実装による失敗を失敗証拠として記録する試験を含む。
  これはAI編集やIssue-to-PRが通ったという実証ではない。
