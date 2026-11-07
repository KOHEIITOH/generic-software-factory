# 0032: 永続intentと外部照合を配送フローへ接続する

trusted controller専用のdeliver_draftを追加する。DeliveryGuardsが正確なartifact・
信頼された証跡・現在有効な配送権限を検証しなければ、配送を始めない。
モデルの自己申告やHTTPリクエストのbooleanは受け取らない。Guard実装とoperator認証を
持つローカル実行入口への接続は後続とし、この関数単体をWebへ公開しない。

同一planとrepository権限・base revisionを確認し、commit準備→branch→Draft PRの順に
進める。外部書込前のpending保存とCASを必須とし、branch/PRは正確なread-back照合後に
receiptを保存する。baseの変更、Guardの失効、remote branchの変更があれば停止する。
Guardは最初・branch作成前・PR作成前に再検証する。

commit準備の結果不明は再送しない。branch_pending/pr_pendingはremote照合のみで復旧し、
見つからなくても再送しない。結果不明はrepoの直列枠を保持する。deliveredの再呼出しも
外部の正確なDraft PRを照合し、書き込まない。commit/PRの本文はcontrollerが固定生成し、
モデル生成の任意テキストを配送権限として扱わない。

API fixtureと実File保存で、正常配送、再呼出し、Guard不足/失効、stale base、結果不明、
不一致receipt、branch改変、未発見時の再作成なしを確認する。実AI/実Docker/実GitHubの
通し試験ではない。
