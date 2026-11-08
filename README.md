# Generic Software Factory

**AI-Native Software Development Platform — 汎用AIソフトウェア開発プラットフォーム**

Generic Software Factoryは、ソフトウェア開発の計画・実行・品質・承認・成果物を統制する独立した開発プラットフォームです。人間とAIの両方がFactoryを利用でき、Factory自身も複数のAI Agent Runtimeを交換可能な実行手段として利用します。

> Factoryが開発プロセスの制御主体です。AIはFactoryの一部ではなく、Factoryが利用・統制する交換可能な能力です。

## 基本コンセプト

- **Factory is Independent** — Factoryは特定のAIサービスやAIホストの内部に依存しない。
- **Human & AI Accessible** — 人間はCLI / Slack / APIから、AIはMCP / APIからFactoryを利用できる。
- **AI is Pluggable** — Codex、Claude Code、GitHub Copilot、Gemini CLI、Grok Build等を共通Adapter経由で利用する。
- **Core Owns Orchestration** — Task、Workflow、Policy、Approval、Auditの正本はFactory Coreが持つ。
- **Development First** — まずソフトウェア開発に特化し、汎用業務自動化への拡張は実証後に検討する。

## アーキテクチャ

- **Inbound Interface**: CLI、MCP Server、API / SDKなど、Factoryを操作する入口。
- **Factory Core**: Task / Workflow / Run / Release、Policy、Approval、Retry、Auditを管理。
- **Agent Runtime Adapter**: FactoryからCoding AgentやCustom Agentへ開発作業を委譲。
- **Model Provider Adapter**: 必要な場合にCustom Agent等からモデル推論を利用する接続先。AWS Bedrock、xAI API等を想定。
- **Other Adapters**: Source Control、Execution、Knowledge、Observability等。
- **Project Bootstrapper / Harness**: 既存プロジェクトの分析、Project Profile、Requirements、Architecture、開発規約を管理。

入口（Inbound Interface）とAIへの委譲（Outbound Agent Runtime）は分離します。MCP ServerはAIがFactoryを操作する入口であり、Codex / Claude Code等はFactoryが作業を委譲するRuntimeです。

詳しくは[アーキテクチャ](docs/architecture.md)、[Adapter・Interface契約](docs/adapter-contracts.md)、[Agent対応ロードマップ](docs/agent-runtime-roadmap.md)、[設定](docs/configuration.md)、[セキュリティ](docs/security.md)、[MVP計画](docs/mvp-plan.md)を参照してください。
初めての方向けに[利用ガイド (HTML)](USER_GUIDE.html) と [初回オンボーディング（HTML）](ONBOARDING.html)（[開発者向けMarkdown](ONBOARDING.md)）も用意しています。
[ローカルリポジトリの読み取り専用解析](docs/local-repository-analysis.md)も利用できます。

## 現在の実装方針

- Factory Core / Local CLI: Python 3.11+（初期開発はPython 3.13）
- Dependency / quality tools: uv、pytest、Ruff、Pyright、pip-audit
- Agent Runtime Adapter: Codex CLI、Grok Build CLI、GitHub Copilot SDK（IssueのRunから選択可能。Copilotは空workspace・tools無効の現段階に限る）
- 追加予定: Claude Code、Gemini CLI
- Model Provider: AWS Bedrock ConverseとツールなしCopilot SDK。xAI API等は将来の追加候補
- ローカルWeb UI: React / TypeScript / Vite（Issue取り込み・閲覧。実装実行は明示的なローカルCLI）
- Task Source: GitHub Issues Adapterと重複防止付き取り込み。WebでのIssue取り込みと、明示設定したローカルCLIの開発入口に対応。
- 初期検証: 一時ディレクトリ内のread-only / サンプル限定code-edit smoke test。会社のソースコードは使用しない。

## Quickstart — macOS / Windows / Linux

必要なものは **Git、uv、Python 3.11以上** です（以下は3.13を使用）。最初の確認はAIアカウント不要の `sf --help` とPythonテストから始められます。Codex / Grok / Copilotの接続テストには、各ツールの別途インストールと認証が必要です。

### 1. ツールの準備

| OS | Git / uv の導入 |
| --- | --- |
| macOS | Homebrewがある場合: `brew install git uv` |
| Windows | PowerShell: `winget install --id Git.Git -e`、`winget install --id astral-sh.uv -e` |
| Linux | ディストリビューションのパッケージマネージャーでGitを導入。uvは[公式インストール手順](https://docs.astral.sh/uv/getting-started/installation/)を参照 |

Windowsは**PowerShell**、macOS / Linuxは通常のターミナルで実行します。導入後はターミナルを開き直し、`git --version` と `uv --version` を確認してください。Pythonはuvがインストールします。

### 2. 共通セットアップ（3 OS）

```text
git clone https://github.com/KOHEIITOH/generic-software-factory.git
cd generic-software-factory
uv python install 3.13
uv sync --python 3.13 --extra dev
uv run sf --help
uv run pytest
uv run sf doctor
```

上記はターミナルに**1行ずつ**入力します。WindowsでもPowerShellで同じコマンドを使用できます。`doctor` は追加のAgent CLIが未導入の場合、その不足を報告することがあります。

### 3. 任意：AI Runtime接続テスト

`uv run sf runtime list` で登録済みRuntimeとローカルの実行前提を一覧できます。認証状態や実際の実行成功は判定しません。

**接続候補を網羅した一覧（実装済み・未実装・Model Providerの区別、公式リンク、認証方法）は[オンボーディングのAI接続ガイド](ONBOARDING.md#4-接続するaiを選ぶ任意)を参照してください。**

利用するRuntimeだけを公式手順でインストール・認証してください。[Codex CLI](https://developers.openai.com/codex/cli/)を利用する場合:

```text
codex login
uv run sf codex-smoke
```

Grok Buildは[公式CLIガイド](https://docs.x.ai/build/cli)、CopilotはGitHub Copilot CLIの公式ガイドに従って導入・認証してください。Copilot SDKを利用する場合:

```text
uv sync --python 3.13 --extra dev --extra copilot
copilot login
uv run sf copilot-smoke
```

開発依頼はGitHub Issueで管理します。独立Taskの作成CLIは廃止しました。実行は[PCでのIssue開発](docs/local-issue-development.md)を参照してください。

**対応状況:** Pythonベースのセットアップ手順を3 OS向けに記載していますが、Windows / Linuxでの全Runtime・全機能の実機動作保証ではありません。特にOS依存のCLI、サンドボックス機能、ファイル操作は環境ごとの検証が必要です。まず[オンボーディング](ONBOARDING.md)を確認してください。

## GitHubを初期標準にする方針

Task SourceとSCMの初期標準はGitHubです。GitHub固有のAPI・型・認証・origin照合はAdapterへ
閉じ込め、Core/共通WorkflowはTaskSource・Repository・SourceControl契約を使います。
通常の起動コマンドは変わりません。認証が必要な操作は既存の`GH_TOKEN`または`GITHUB_TOKEN`を使います。
[対応範囲・完了条件と検証](docs/github-first-integration-policy.md)を参照してください。

## WebとDBなしのローカル保存

通常の起動は `uv run sf web --rebuild` のままです。新しい保存先では、対応するPOSIX環境で
File Adapterを自動選択し、Issue参照・Project/Repository・Runの結果をDBなしで保存します。
新しいIssue形式のSQLiteがある場合はSQLiteを使います。旧Task形式は移行せず、新しい保存先を指定します。非POSIX環境の新規保存先もSQLiteです。

[Webでの確認方法・保存先設定・制約](docs/local-web-storage.md)を参照してください。
独立TaskのAPI・CLI・保存構造は削除済みです。[外部Issueモデルと旧形式の扱い](docs/external-issue-model.md)を参照してください。
Harness承認・prepared RunもFile保存に対応。source snapshot・品質/レビュー証跡もFile対応です。ローカルCLIには実装・挙動テスト・独立レビュー・Draft PR配送を接続しています。実サービスでの最終通し試験はPCで未確認です。
要件の子Issue分割・同じPRへの有限レビュー修正・Project/Repository/directory Harnessは
[有限Issueワークフロー](docs/bounded-issue-workflow.md)を参照してください。

## 現在のステータス

**実験的MVP** — ローカルFile/SQLiteによるIssue/Run/Audit記録、Codex/Grok/Copilot Runtime Adapter、read-only smoke test、Codexによるサンプル限定のコード編集と単体テストを実装しています。`uv run sf analyze /path/to/repository --confirm-send` は指定されたローカルGitリポジトリから制限付きのテキストsnapshotをCopilotへ渡して解析します。SDK toolsは無効で、リポジトリ本体をworkspaceとして渡さず、Task/RunやFactory DBにはソース内容を保存しません。ファイルの編集・任意コマンド実行・隔離保証はありません。詳細は[解析の範囲と制約](docs/local-repository-analysis.md)を参照してください。`uv run sf dev-smoke --runtime codex` は使い捨て一時ディレクトリ内の同梱サンプルだけを編集します。編集可能なRuntimeは明示指定が必要で、現時点ではCodexのみ検証済みです。Factory Coreおよび共通AgentRuntime契約はCodexに依存しません。明示的なローカルoperator設定を使う `sf issue develop` には、Issue取得・AI変更案・実隔離の挙動テスト・別session/requestのレビュー・Draft PR配送/復旧を接続しました。実Bedrock/実GitHubでの最終通し成功はPCで未確認です。Webからの実装実行、失敗の自動修正ループ、MCP Serverは未実装です。

## ローカルWeb UI（閲覧専用）

```bash
uv sync --extra web
uv run sf web --rebuild
```

ブラウザで `http://127.0.0.1:8000/` を開きます。画面には外部Issue、実行履歴、登録済みRuntimeが表示され、`/guide` と `/onboarding` からHTML資料を読めます。初回またはフロントエンド再構築時はNode.js/npmも必要です。ローカルAPIは認証なしのため外部公開しないでください。詳細は[ローカルWeb API](docs/local-web-api.md)を参照してください。

## GitHub Issuesとローカル開発

Issue取り込みは[GitHub Issues Adapterガイド](docs/guides/github-issues-source.md)を参照してください。
ローカルでの実装・テスト・レビュー・Draft PRは、[PCでの設定・実行・復旧手順](docs/local-issue-development.md)を使います。

```sh
uv run sf issue develop --config /absolute/path/to/operator-config.json --confirm-run --confirm-bedrock
```

Bedrock推論はPCのAWS認証を使い、課金が発生し得る明示操作です。Web閲覧の起動にこの追加手順は不要です。

## セキュリティの基準

- 信頼できないコードは分離された実行環境内でのみ実行する。
- 最小権限の認証情報とSecret参照を使い、平文Secretを設定に保存しない。
- ネットワークアクセスは既定で制限する。
- Merge、本番Deploy、破壊的操作、Policy変更には人間の承認を必須とする。
- タスク入力、リポジトリ内容、ツール出力、モデル出力は信頼できないデータとして扱う。
- 決定的なQuality Gateを必須とする。Agent自身によるレビューだけでは不十分。

## リポジトリ構成

```text
core/          Coreの契約とライフサイクル仕様
adapters/      外部Runtime・サービスとのAdapter契約
harness/       再利用可能な指示、Policy、知識テンプレート
agents/        Agent製品に依存しないRole定義
workflows/     再利用可能なWorkflow定義
config/        デプロイ設定の例
quality/       Quality Gateの仕様とテンプレート
docs/          アーキテクチャ、契約、セキュリティ、ADR、ロードマップ
src/           Python Core / CLI / Runtime Adapter
```

## コントリビューション

Core契約、セキュリティPolicy、Workflowの意味を変更する場合は、Architecture Decision Record (ADR)が必要です。

## 公開と利用条件

このリポジトリはソースコードの閲覧・評価を目的として公開する予定です。**公開はオープンソースライセンスの付与を意味しません。** 著作権者から別途許可を得ない限り、GitHubの利用規約や適用法令で認められる範囲を超える複製・改変・再配布等の権利は付与されません。社内利用や業務コードへの適用には、所属組織の承認とAIサービス利用規程の確認が必要です。
