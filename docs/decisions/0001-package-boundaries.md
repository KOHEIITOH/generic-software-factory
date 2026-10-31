# ADR-0001: パッケージの境界

- ステータス: v0.1で承認済み
- 決定: Factory Core、Factory Adapters、Factory Configurationを分離する。
- 背景: パッケージは、特定のAIベンダー、Agent製品、対象プロジェクトから独立している必要がある。
- 影響:
  - Coreはライフサイクル、Policy、状態、Workflowの意味を担う。
  - Adapterはベンダー／製品との連携を担う。
  - ConfigurationはAdapterとプロジェクト固有の動作を選択する。
  - Harnessは指示／コンテキストを提供するが、オーケストレーションを代替しない。
  - Adapter契約にはバージョンを付け、適合性テストを行う必要がある。
