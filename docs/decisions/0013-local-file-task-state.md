# ADR-0013: File Task保存は排他・atomic replace・明示した範囲で提供する

- 状態: 採用（マージ後）。AWS portability P02のTask保存プレビュー。

StateStoreの同じ契約に対し、追加DBなしでcreate/get/import-onceを実装する。
同一local filesystemでflockとfile/directory fsyncを使い、Task/source/eventを1 recordへ保存する。
外部取込みはexact identityの安定IDをkeyにして、二つのファイルへの非原子的なindex追加を避ける。
保存内容が異なるkey衝突や、壊れた/未知versionのrecordは上書きしない。

SQLiteを使う残りのFactoryへ部分backendを注入せず、別の`sf state`入口を提供する。
`sf task`/Web/Run/承認の動作は変えない。File CLIでsqlite3.connectを呼ばないことを試験する。
Fileの更新/CAS・原子的承認・完全なbackend選択・旧データのexport/importは次段階とする。

初期はPOSIX local filesystemに限定し、未対応OSやlock不可時は拒否する。
将来、Windows等へ広げる場合も同じ契約/障害試験を満たし、soft lockへ暗黙に落とさない。
