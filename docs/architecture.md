# アーキテクチャ — Generic Software Factory v0.1

## 1. 製品の定義

Generic Software Factoryは、再利用可能な開発ファクトリーのパッケージです。単一のCoding Agent、モデルゲートウェイ、IDE拡張機能、プロジェクトテンプレートではありません。差し替え可能な機能を組み合わせ、統制されたWorkflowを調整します。

デプロイ時には、次を指定します。

- 1つ以上のAgent Runtime
- 任意のモデルProviderへの直接アクセス
- ソース管理対象のリポジトリ
- 分離された実行バックエンド
- プロジェクト固有のコンテキストと品質チェック用コマンド
- 承認PolicyとセキュリティPolicy

パッケージは、ビルド時にこれらの選択肢が決まっていることを前提にしてはいけません。

## 2. アーキテクチャ原則

| 原則 | 必須の性質 |
|---|---|
| ベンダー非依存 (Vendor Agnostic) | ProviderやRuntime固有の動作はAdapterの内側に置く。 |
| プロジェクト非依存 (Project Agnostic) | 言語／フレームワークのコマンドや規約は、設定またはプロジェクトのコンテキストとする。 |
| モジュール化 (Modular) | コンポーネントはバージョン付き契約を介して連携する。 |
| 設定可能 (Configurable) | Coreにプロジェクト固有のSecretや前提を埋め込まない。 |
| 自己改善 (Self-improving) | 実行の証跡から改善を提案できる。CoreやSafety Policyの変更にはレビューを必須とする。 |

## 3. パッケージの境界

### Factory Core

タスクのライフサイクル、Workflowの遷移、Policy適用、承認、監査イベント、再試行、タイムアウト、キャンセルを担います。CoreはProvider SDKやプロジェクト固有のコードをimportしてはいけません。

### Factory Adapters

安定したFactory契約を、ベンダー／製品固有のAPIへ変換します。

- AgentRuntime
- ModelProvider (任意)
- SourceControl
- Execution
- Observability

### Factory Configuration

デプロイで使うAdapter実装、プロジェクトプロファイル、Workflow、Policyを選択して接続します。

### Harness

共通原則、Roleの指示、プロジェクトのコンテキスト、エンジニアリング標準、制約、ツール利用の指針を提供します。Harnessはオーケストレーターではありません。

## 4. 論理アーキテクチャ

```text
                    HUMAN / OPERATOR
              目標、承認、Policyの判断
                            |
                            v
+-------------------------------------------------------+
|                 FACTORY CONFIGURATION                 |
| project | runtime | provider | workflow | policies    |
+-------------------------------------------------------+
                            |
                            v
+-------------------------------------------------------+
|                    FACTORY CORE                       |
| オーケストレーター | Task State | Policy Engine | Audit Log |
| Workflow Engine | Approval Gate | Retry / Recovery    |
+-------------------------------------------------------+
           |                |                 |
           v                v                 v
     Agent Adapter     SCM Adapter      Execution Adapter
           |                |                 |
           v                v                 v
     Agent Runtime      Git Provider      Isolated Sandbox
           |
           v
    Model Provider Adapter (任意。Runtimeがモデルアクセスを担う場合あり)

Harness: Roleの指示、プロジェクトのコンテキスト、標準、制約。
Quality Gates: 決定的なチェックと、独立して記録されたレビュー。
```

## 5. Workflowのライフサイクル

最小限の状態:

`CREATED → VALIDATING → PLANNING → PLAN_REVIEW → IMPLEMENTING → TESTING → REVIEWING → PR_READY → APPROVAL_PENDING → COMPLETED`

制御状態: `BLOCKED`、`FAILED`、`CANCELLED`、`RETRYING`。

すべての遷移について、run/task ID、遷移前後の状態、実行者、タイムスタンプ、理由、証拠／成果物への参照、Policyの判断を記録します。

## 6. 論理Agent Role

- **Planner** — リクエストをスコープ付きのタスクと受け入れ条件に整理します。
- **Architect** — 制約、依存関係、設計上の影響を特定します。
- **Developer** — 承認された作業を実装します。
- **Tester** — テストを作成／実行し、証拠を報告します。
- **Reviewer** — diffと証拠を独立してレビューします。
- **Security Reviewer** — セキュリティに関わる変更を確認します。

これらはRoleの定義であり、製品名ではありません。デプロイ時に、複数のRoleを1つのRuntimeに割り当てたり、1つのRoleを複数のAgentに割り当てたりできます。

## 7. Quality Gate

設定の検証、計画の承認、test/lint/type check/build、Secret／依存関係／セキュリティのチェック、diffのレビュー、マージ／デプロイ／破壊的操作に対する人の承認を行います。

Agentの申告は証拠の一部であり、Gateの確定結果ではありません。決定的なコマンド出力と、独立して記録されたレビュー結果を優先します。

## 8. 拡張モデル

各Adapterは、ID、type、契約バージョン、対応機能、設定スキーマ、必要な権限、ヘルスチェックの動作、正規化されたエラー、再試行可否を宣言します。

不明な機能が要求された場合は、許可せずに失敗させます。Coreは検証時に互換性のない契約バージョンを拒否します。

## 9. v0.1の対象外

- 完全自律型の本番デプロイ
- 複数Agentによる議論／swarm動作の必須化
- あらゆるProvider／Runtimeへの組み込み対応
- 汎用IDEまたはプロジェクト生成ツール
- 人のレビューを経ないCoreコードまたはセキュリティPolicyの自己変更
