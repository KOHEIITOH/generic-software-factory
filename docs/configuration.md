# 設定モデル — v0.1

設定はデプロイごとに異なります。パッケージは例とスキーマを提供し、実際のRuntime、リポジトリ、Provider、プロジェクトの選択は利用者が指定します。

## 設定レイヤー

1. `factory.yaml`: デプロイ単位の接続設定とPolicy。
2. `project.yaml`: プロジェクト固有のコマンド、規約、パス。
3. Harnessファイル: 指示と知識を記した文書。
4. Secret Store／環境変数: 認証情報 (YAMLに平文で記載しない)。

## `factory.yaml` の例

```yaml
apiVersion: generic-software-factory/v1alpha1
kind: Factory
metadata:
  name: my-factory
spec:
  runtime:
    agent:
      adapter: "<agent-runtime-adapter>"
      config: {}
    modelProvider:
      enabled: false
      adapter: null
      config: {}
  sourceControl:
    adapter: "<source-control-adapter>"
    config:
      provider: "<git-provider>"
      repository: "<owner>/<repository>"
      baseBranch: main
      credentialRef: "env:FACTORY_GIT_TOKEN"
  execution:
    adapter: "<execution-adapter>"
    config:
      isolation: required
      workspaceTtlMinutes: 60
      networkAccess: restricted
  workflow:
    definition: workflows/issue-to-pr.yaml
    maxRetries: 1
    requirePlanApproval: true
    requireHumanApprovalBeforeMerge: true
  harness:
    path: harness
  quality:
    gates:
      - id: tests
        required: true
        commandRef: project.test
      - id: lint
        required: true
        commandRef: project.lint
      - id: security
        required: true
        adapter: "<security-check-adapter>"
  policy:
    permissions: least-privilege
    allowProductionAccess: false
    requireApprovalFor:
      - git.merge
      - deployment
      - destructive-command
      - policy-change
  observability:
    adapter: "<observability-adapter>"
    retentionDays: 30
```

## `project.yaml` の例

```yaml
apiVersion: generic-software-factory/v1alpha1
kind: ProjectProfile
metadata:
  name: example-project
spec:
  repositoryRoot: .
  language: "<language>"
  framework: "<framework>"
  architectureDocs: []
  commands:
    test: "<project-test-command>"
    lint: "<project-lint-command>"
    build: "<project-build-command>"
  conventions:
    - "新しい抽象化を導入する前に、既存のパターンに従ってください。"
    - "明示的な要件がない限り、公開APIを変更しないでください。"
  definitionOfDone:
    - "受け入れ条件を満たしている。"
    - "必須のQuality Gateを通過している。"
    - "既知の制約が文書化されている。"
```

## 検証ルール

- 未知のAPI versionまたはkindは拒否します。
- 必須のAdapter参照先が解決できることを確認します。
- Adapterの設定を、そのAdapterのスキーマに照らして検証します。
- 認証情報は参照として指定し、値を直接記載してはいけません。
- 分離実行からホスト実行へ暗黙にフォールバックしてはいけません。
- 本番アクセスと破壊的操作は、明示的に許可されない限り拒否します。
- プロジェクトのコマンドは、設定された実行境界内でのみ実行します。
