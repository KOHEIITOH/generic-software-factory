# Generic Software Factory

**汎用AIソフトウェア開発プラットフォーム (Generic AI Software Development Platform)**

設定可能なAIエージェント、モデルプロバイダー、リポジトリ、実行環境を横断して、統制されたソフトウェア開発ワークフローを実行するための、再利用可能でベンダーやプロジェクトに依存しないパッケージです。

> Factoryは**作業をどのように統制し、届けるか**を定義します。デプロイ時に、**どのエージェント、モデル、リポジトリ、ツールで作業するか**を指定します。

## 設計原則

1. **ベンダー非依存 (Vendor Agnostic)** — 特定のAIベンダーやAgent Runtimeへの依存を必須にしない。
2. **プロジェクト非依存 (Project Agnostic)** — 特定の言語、フレームワーク、リポジトリへの依存を必須にしない。
3. **モジュール化 (Modular)** — Coreのオーケストレーション、Adapter、Policy、Workflowの境界を明確にする。
4. **設定可能 (Configurable)** — デプロイ固有の選択は設定で与える。
5. **自己改善 (Self-improving)** — 実行の証跡から改善を提案できる。CoreやSafety Policyの変更にはレビューを必須とする。

## アーキテクチャ

- **Factory Core**: Workflowのライフサイクル、タスク状態、Policy適用、監査イベント、再試行、承認を担います。
- **Factory Adapters**: Agent Runtime、Model Provider、ソース管理、実行環境、可観測性との連携を担います。
- **Factory Configuration**: デプロイ固有のプロジェクト、Runtime、Provider、Workflow、Policyの設定を担います。
- **Harness**: 共通の指示、ドメインの背景情報、エンジニアリング標準、ツール利用上の制約を提供します。
- **Quality Gates**: 作業の次の段階への進行前に、決定的なチェックと独立したレビューを行います。

[アーキテクチャ](docs/architecture.md)、[設定](docs/configuration.md)、[Adapter契約](docs/adapter-contracts.md)、[セキュリティ](docs/security.md)、[MVP計画](docs/mvp-plan.md)を参照してください。
初めての方向けに、[利用ガイド (HTML)](docs/user-guide.html)も用意しています。

## ステータス

**v0.1 — 仕様を先行させた初期構成。** 最初の実装では、Providerやプロジェクトの選択肢を置き換え可能に保ちながら、エンドツーエンドのWorkflowを1つ実証します。CLIとリファレンスAdapterはまだ実装されていません。

## CLIの予定

```bash
sf init
sf validate --config factory.yaml
sf doctor --config factory.yaml
sf run --config factory.yaml --task "Implement the requested change"
sf status <run-id>
sf cancel <run-id>
```

これらのコマンドは予定しているインターフェースを示すもので、この仕様先行の初期構成ではまだ実装されていません。

## 安全性の基準

- 信頼できないコードは、分離された実行環境内でのみ実行する。
- 最小権限の認証情報とSecret参照を使い、平文のSecretを設定に保存しない。
- ネットワークアクセスは既定で制限する。
- マージ、デプロイ、破壊的操作、Policy変更には人の承認を必須とする。
- タスク入力、リポジトリ内容、ツール出力、モデル出力は信頼できないデータとして扱う。
- 決定的なQuality Gateを必須とする。エージェント自身によるレビューだけでは不十分。

## リポジトリ構成

```text
core/          Coreの契約とライフサイクル仕様
adapters/      連携契約とAdapterのドキュメント
harness/       再利用可能な指示、Policy、知識テンプレート
agents/        Agent製品に依存しないRole定義
workflows/     再利用可能なWorkflow定義
config/        デプロイ設定の例
quality/       Quality Gateの仕様とテンプレート
docs/          アーキテクチャ、セキュリティ、設定、ロードマップ、ADR
```

## コントリビューション

Core契約、セキュリティPolicy、Workflowの意味を変更する場合は、Architecture Decision Record (ADR)が必要です。
