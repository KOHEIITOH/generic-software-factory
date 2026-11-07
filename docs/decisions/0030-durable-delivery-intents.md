# 0030: 外部配送の前にintentを永続化する

## 決定

DeliveryStateは配送の記録とCASだけを担う。認証・品質判定・承認を兼ねない。
初期FileDeliveryStateは既存のno-follow JSON保存、fsync、POSIX process lockを再利用し、
専用DBを作らない。既存dashboard schemaは変更せず、同じdata rootのdelivery-v1へ置く。
将来のS3/DB Adapterも同じatomic claim/CAS契約を実装する必要がある。

trusted controllerはcanonical repository identityと検証済みDeliveryPlanでclaimする。
未解決の同一repositoryがあれば別Runも拒否する。ネットワーク操作中にlockは保持せず、
各外部書込の前にpending状態を確定する。commit/branch/PRのreceiptを段階的に保存する。
同じRunの再claim、別planへの差替え、逆行、段階飛ばし、古いWorkerのCASを拒否する。

## 復旧

claimed: commit準備の結果不明を含む。branch_pending/pr_pending: 外部書込が成功して
receipt保存前に停止した可能性がある。再起動で初期化・再送・期限による自動解放をしない。
次のcontroller実装が、正確なbranch/revisionとDraft PR markerを実サービスで照合して
receiptを保存する。照合不能なら停止し、未解決のrepoを解放しない。

既存ディレクトリ内のstate欠落・破損・未知schemaを空状態へ戻さない。fsync結果不明も
成功扱いしない。ローカルPOSIXの同一data rootだけが対象で、別PC/別root/分散Workerを
直列化する保証はない。ECSには別途durable volumeか同等CASを持つAdapterが必要。

## 検証

再起動、receipt照合、同一repo直列、他repo、段階/planのCAS、破損・symlink・欠落、
replace後のfsync失敗、別processによる同時claimをテストする。実配送や実AIは呼び出さない。
