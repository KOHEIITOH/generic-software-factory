# 設定モデル — v0.1

初期のTask Source / SCMはGitHubが既定です。Providerを選ぶ追加設定なしに、
`uv run sf web --rebuild`で既存のGitHub UIを利用できます。対象Repositoryは利用者が選び、
認証が必要な操作にはサーバー側の`GH_TOKEN`（優先）または`GITHUB_TOKEN`を使います。
公開Issueの読取は引き続き匿名でも可能です。起動だけでGitHub APIやAIを呼び出しません。

実際の既定Adapterは`integration_defaults.py`で組み立てます。任意の確認コマンド
`uv run sf integration show`と`GET /api/integrations`はProvider名・認証設定の有無だけを表示し、
トークン値を出しません。`authenticated: not_checked`は認証未検証を意味します。

以下のYAMLは将来のデプロイ設定モデルの例です。**現行CLI/Webはfactory.yamlを自動読込しません。**
ファイルを書くだけで実行設定が切り替わるとは扱わないでください。Runtime/Execution/Policyの
選択と、実装済みの環境変数設定はそれぞれの実行入口の要件に従います。

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
  taskSource:
    adapter: github
    config:
      repository: "<owner>/<repository>"
      credentialRef: "env:GH_TOKEN"
  sourceControl:
    adapter: github
    config:
      repository: "<owner>/<repository>"
      credentialRef: "env:GH_TOKEN"
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
