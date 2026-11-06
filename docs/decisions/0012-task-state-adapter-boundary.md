# ADR-0012: Task保存の最小StateStore境界から段階移行する

- 状態: 採用（マージ後）。AWS portability P01。

FactoryのTask作成/取得/外部取込みを、TaskRecordと業務操作を返すStateStore契約へ移す。
初期Adapterは既存schema互換のSqliteStateStoreで、ID・prompt・外部identityの一意性と
auditを保つ。外部取込みは同じtransaction内でcreate-if-absentと記録を行う。
SQL connectionやsqlite例外を契約へ返さず、保存失敗をStateUnavailableへ正規化する。

現時点の契約はTask操作だけであり、完全なFactory backendの切替ではない。
Run/承認/Project/証拠は引き続きSQLite。部分実装のFile StoreをFactoryへ注入して
二つの保存先を黙って混在させる入口は追加しない。
次PRのFile実装は同じcontract testと明示したTask保存用CLIで検証する。
