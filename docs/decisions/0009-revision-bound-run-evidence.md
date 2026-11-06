# ADR-0009: 品質証拠はRun・対象版・試行に固定して追記する

- 状態: 採用（マージ後）。R09a。

既存QualityEvidenceはcheck IDとbool中心で、Runの版や実行件数に結び付いていない。
これを変更して既存利用者へ影響を与えず、信頼されたcollectorの記録を先に追加する。

prepared Runへ不変の計画を登録し、実装後対象commit/Harness/差分、collector、必須チェック、
最大3試行を固定する。結果は追記のみ、全必須結果は同じ最新試行から集める。
0件/不明件数のテストやskippedを成功にしない。collectorと評価対象の不一致は拒否する。
保存済みデータを既存Quality Gateへ変換して再利用する。

サービス単体はreportの真正性やcommitの由来を証明しない。controllerからの検証済み入力が前提。
独立レビュー、成果物、隔離実行が接続されるまでdelivery適格にはしない。
Docker制約のため実行接続を止めている間も、この記録・集約経路の実Git/DB試験を進められる。
