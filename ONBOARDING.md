# 初回オンボーディング — Generic Software Factory

> 対象: 初めてFactoryを触る人。所要目安15〜30分（AI Runtimeのインストール時間を除く）。
> 本書は実験的MVP向けです。業務・機密リポジトリでの運用手順ではありません。

## 0. 何ができる？

FactoryはAI開発作業の工程・権限・品質判定を共通化する基盤です。
登録済みの実行設定で、GitHub Issueから実装・隔離テスト・独立レビュー・Draft PRまで進められます。
実Bedrock＋GitHubの最終通し確認は利用者のPCで行います。完全自律開発の完成を意味しません。

## 現在のWeb UIでできること（2026年11月時点）

初回に[実行設定と認証](docs/local-web-execution.md)を登録し、`uv run sf web --rebuild`で起動します。
ターミナルの操作リンクから開き、Issueを選んで「同意して実行・Draft PR作成」を押します。
手動取り込み・Repositoryの手動紐付け・デモPR作成は不要です。

- 通常操作: Issue選択、実行、進捗・PRリンク、停止・復旧・履歴の確認
- 詳細操作: 診断、要件分割と計画承認、同じPRのレビュー修正
- Project管理: 任意。画面を開いたときだけ読み込みます
- `/guide`、`/onboarding`: ブラウザで利用手順を確認

初期設定にはCLI操作が必要です。loopback専用で、実行にはoperator認証が必要です。
WebのビルドにはNode.js/npm、コードの検証には資源制限を強制できるDockerが必要です。

## 1. 最初に用意する

- Git と uv（[READMEのOS別手順](README.md#quickstart--macos--windows--linux)）
- macOS / Linux のターミナル、または Windows PowerShell
- Python 3.13 は `uv python install 3.13` で導入
- 最初のローカルテストにAIアカウントは不要

## 2. 最初の5コマンド

以下を上から順に実行します。PowerShell / macOS / Linux共通です。

```text
git clone https://github.com/KOHEIITOH/generic-software-factory.git
cd generic-software-factory
uv python install 3.13
uv sync --python 3.13 --extra dev
uv run sf --help
```

`sf --help` に `doctor`, `task`, `run`, `analyze` などのサブコマンドが表示されれば、CLI起動は成功です。

## 3. AIなしで動作を確かめる

```text
uv run pytest
uv run ruff check .
uv run pyright
```

テストが成功すれば、少なくともPython基盤の検証は通っています。各AI Runtimeの動作はまだ確認できていません。

## 4. 接続するAIを選ぶ（任意）

### 4-1. まず「Agent Runtime」と「Model Provider」を区別する

**Agent Runtime** は計画・コード生成・ツール操作などを担当する実行ソフトウェアです。**Model Provider** は推論モデルを提供する接続先です。たとえば「Claude Code（Runtime）」と「Anthropic API（モデル提供）」は別の層です。Factory Coreは特定の製品に依存せず、Adapterで差し替える設計です。

**重要:** 下表の「接続済み」はFactoryの限定的なAdapterが存在するという意味です。全自動開発、任意リポジトリ編集、OSレベルの隔離、Windows/Linuxでの動作保証を意味しません。

### 4-2. Coding Agent / Agent Runtime 一覧

| 候補 | Factory実装状況 | Factoryでの実行方法 | 導入・認証 | 現時点の注意 |
| --- | --- | --- | --- | --- |
| **OpenAI Codex CLI** | **接続済み** | CLI Adapter、read-only smoke / 限定fixture編集 | [公式Codex CLI](https://developers.openai.com/codex/cli/)で導入、`codex login` | 実リポジトリへの自律編集は未対応 |
| **xAI Grok Build CLI** | **接続済み** | CLI Adapter、read-only smoke | [公式Grok CLI](https://docs.x.ai/build/cli)で導入、`grok login` | ツール許可リストによる制限。OS隔離ではない |
| **GitHub Copilot SDK / CLI** | **接続済み** | Python SDK Adapter、空workspace・ツール無効 | [GitHub Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli)で導入、`copilot login` | SDK依存の追加インストールが必要 |
| **Anthropic Claude Code** | **未実装・追加候補** | 将来CLI / SDK Adapter | [公式Claude Code](https://docs.anthropic.com/en/docs/claude-code/overview) | Factory用 `sf claude-smoke` は存在しない |
| **Google Gemini CLI** | **未実装・追加候補** | 将来CLI Adapter | [公式Gemini CLI](https://github.com/google-gemini/gemini-cli) | Factory用 `sf gemini-smoke` は存在しない |
| **OpenAI Agents SDK等のCustom Agent** | **未実装・構想** | 独自Runtime Adapter | [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/) | 独自のツール権限・監査・隔離設計が必要 |
| **その他のCoding Agent** | **未実装・拡張候補** | 共通契約を実装するAdapter | 製品ごとの公式資料 | 対応を約束するものではない |

### 4-3. Model Provider / モデル接続先（将来の拡張）

Agent Runtimeとは別に、Custom Agentが直接推論APIを呼ぶ場合の候補です。**Bedrock ConverseとツールなしCopilot SDKのModel Providerを実装しています**。その他は追加候補です。

| 候補 | 接続方法の想定 | 役割 |
| --- | --- | --- |
| OpenAI API | API Adapter | OpenAIモデルを直接呼び出す |
| Anthropic API | API Adapter | Claudeモデルを直接呼び出す |
| Google Gemini API / Vertex AI | API Adapter | Gemini系モデルを利用する |
| AWS Bedrock | AWS SDK Adapter | AWS経由で対応モデルを利用する |
| xAI API | API Adapter | Grokモデルを直接呼び出す |
| Azure AI Foundry等 | Provider Adapter | 組織のクラウド基盤を利用する |
| ローカル推論基盤（例: Ollama） | ローカルHTTP Adapter | 対応するローカルモデルを利用する |

**BedrockやOllamaを入れただけで、FactoryからCoding Agentとして実行できるわけではありません。** 必要に応じてCustom AgentとRuntime Adapterが別途必要です。各Providerの認証・料金・データ取扱い・モデル提供状況は導入時に確認します。

### 4-4. 現在利用できる3つのRuntimeを試す

利用するものだけを公式手順でインストールし、認証してください。コマンドは各CLIがPATH上にあることを前提とします。

**Codex CLI**

```text
codex --version
codex login
uv run sf codex-smoke
```

**Grok Build CLI**

```text
grok --version
grok login
uv run sf grok-smoke
```

**GitHub Copilot SDK**

```text
uv sync --python 3.13 --extra dev --extra copilot
copilot --version
copilot login
uv run sf copilot-smoke
```

認証・課金・利用可能モデルは各サービスの契約に依存します。CLIごとの対応OSも公式資料を確認してください。Windowsでは一部ツールでWSLが必要になる可能性があり、Factory全体のWindowsネイティブ対応を保証するものではありません。

### 4-5. 選び方と現在の限界

- **まずFactoryの動作を試したい:** Codex CLIを使ったread-only smoke testが最も基本的な導線。
- **異なるRuntimeのAdapterを比較したい:** Grok BuildやCopilot SDKも追加し、同じ無害な入力で接続確認。
- **Claude Code / Gemini CLIを使いたい:** 現在はFactory Adapter未実装。単体での利用とFactory経由の利用を混同しない。
- **AWS Bedrockを使いたい:** Converse Model ProviderとローカルIssue開発CLIを利用可能。PCの認証・設定と通し試験が必要。

**どのAIを選んでも、モデルの回答だけで品質合格としないこと。** Quality Gateは実隔離テストと独立レビューの検証証拠を必要とします。利用するPCでDockerの資源制限と認証を確認します。

詳細: [Agent Runtime / Model Provider対応方針](docs/agent-runtime-roadmap.md)、[Adapter契約](docs/adapter-contracts.md)。

## 5. GitHub Issueを選んで実行する

開発依頼はGitHub Issueで管理します。Factory独自Taskの作成・旧Task CLIは削除済みです。
通常は認証済みWeb画面でIssueを選択して実行します。[初回設定・Web操作](docs/local-web-execution.md)を参照してください。CLIから同じ開発処理を実行することもできます。

```sh
uv run sf issue develop --config /absolute/path/to/operator-config.json --confirm-run --confirm-bedrock
```

[PCでの設定・実行・復旧](docs/local-issue-development.md)を参照してください。
旧Task形式の保存先は移行しません。[新しい保存先](docs/external-issue-model.md)を指定し、実行時にIssueを取得します。

## 6. よくあるつまずき

- `uv` / `git` が見つからない: インストール後にターミナルを再起動し、PATHを確認。
- `sf doctor` でCLI不足: 使わないRuntimeのCLIは不要。使うRuntimeだけ導入。
- 認証エラー: 利用するCLIでログイン。認証情報をチャットやIssueに貼らない。
- Windowsのパス: PowerShellで実行し、Linuxの `/path/to/...` をそのままコピーしない。
- テストがOS依存で失敗: 失敗ログとOS・Python・uvのバージョンを控え、環境差分として調査。

## 7. 安全に使うための境界

Smoke test成功はAIが安全に任意コードを編集・実行できる証明ではありません。開発実行には別途、承認済み設定・実Docker検証・独立レビュー・配送証跡が必要です。会社のコード、個人情報、認証情報は試験用に渡さないでください。リポジトリ解析コマンド `sf analyze` は内容をCopilotへ送信するため、[送信範囲と制約](docs/local-repository-analysis.md)を確認してください。

## 8. 次に読む

- [利用ガイド（図解HTML）](USER_GUIDE.html)
- [アーキテクチャ](docs/architecture.md)
- [セキュリティ](docs/security.md)
- [Quality Gateと改善ループ](docs/quality-improvement-loop.md)
