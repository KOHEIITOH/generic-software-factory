# 初回オンボーディング — Generic Software Factory

> 対象: 初めてFactoryを触る人。所要目安15〜30分（AI Runtimeのインストール時間を除く）。
> 本書は実験的MVP向けです。業務・機密リポジトリでの運用手順ではありません。

## 0. 何ができる？

FactoryはAI開発作業の工程・権限・品質判定を共通化するための基盤です。現状はローカルCLIでTask / Runを記録し、Codex・Grok・Copilotへの限定的な接続確認ができます。Workflow、Policy、Quality Gate、Improvement LoopのPython部品も実装されていますが、これらを統合した完全自律開発CLIやPR自動作成は未実装です。

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

まず1つだけ選び、公式手順でCLIをインストール・認証してください。

| Runtime | 接続確認 | 補足 |
| --- | --- | --- |
| Codex CLI | `codex login` → `uv run sf codex-smoke` | [Codex CLI](https://developers.openai.com/codex/cli/) |
| Grok Build CLI | `grok login` → `uv run sf grok-smoke` | [Grok CLI](https://docs.x.ai/build/cli) |
| GitHub Copilot SDK | `uv sync --extra dev --extra copilot` → `copilot login` → `uv run sf copilot-smoke` | Copilot CLI認証が必要 |

各CLIの対応OS・インストール方法・認証可否は公式資料で確認してください。すべてのOSで各Runtimeが動くことは現時点では保証していません。

## 5. Taskを作成して実行する（任意）

Runtimeの認証後、まず無害な質問で試してください。

```text
uv run sf task create "Explain what this project does"
```

返されたTask IDを控え、例えば次のように実行します。

```text
uv run sf task run <task-id> --runtime codex
```

`<task-id>` は実際のIDに置き換えてください。実行結果とRun IDが表示されます。Task / Runはローカルの `.sf-factory` に記録されます。

## 6. よくあるつまずき

- `uv` / `git` が見つからない: インストール後にターミナルを再起動し、PATHを確認。
- `sf doctor` でCLI不足: 使わないRuntimeのCLIは不要。使うRuntimeだけ導入。
- 認証エラー: 利用するCLIでログイン。認証情報をチャットやIssueに貼らない。
- Windowsのパス: PowerShellで実行し、Linuxの `/path/to/...` をそのままコピーしない。
- テストがOS依存で失敗: 失敗ログとOS・Python・uvのバージョンを控え、環境差分として調査。

## 7. 安全に使うための境界

Smoke test成功はAIが安全に任意コードを編集・実行できる証明ではありません。OSレベルの隔離、証拠の真正性、PR自動作成は未完成です。会社のコード、個人情報、認証情報は試験用に渡さないでください。リポジトリ解析コマンド `sf analyze` は内容をCopilotへ送信するため、[送信範囲と制約](docs/local-repository-analysis.md)を確認してください。

## 8. 次に読む

- [利用ガイド（図解HTML）](USER_GUIDE.html)
- [アーキテクチャ](docs/architecture.md)
- [セキュリティ](docs/security.md)
- [Quality Gateと改善ループ](docs/quality-improvement-loop.md)
