# Agent Runtime / Model Provider 対応方針

## 目的

主要なCoding Agentを選べるようにしつつ、Factory Coreを複雑にしすぎない。最初から全製品・全モデルの組み合わせを抽象化するのではなく、実際に使うRuntimeを順番に追加する。

## 標準対応の対象

| 対象 | 分類 | 方針 | 状態 |
|---|---|---|---|
| OpenAI Codex CLI | Agent Runtime | 最初の実装・ローカル実証対象 | Read-only Adapter |
| Grok Build CLI (xAI) | Agent Runtime | headless CLI経由。ACPは必要になった段階で検討 | Read-only Adapter |
| Claude Code | Agent Runtime | 次のRuntime候補 | Planned |
| GitHub Copilot | Agent Runtime | 既存SDK smoke testを共通契約へ接続 | Planned |
| Gemini CLI | Agent Runtime | 次段階で追加 | Planned |
| AWS Bedrock | Model Provider | Custom Agentからモデル推論を利用する場合に追加 | Planned |
| xAI API (Grok models) | Model Provider | Custom AgentからGrokモデルを直接利用する場合に追加 | Planned |

## 役割を分ける

- **Agent Runtime**: タスクを受け取り、作業・ツール利用・成果物生成を行う実行環境。
- **Model Provider**: Custom Agent等からモデル推論を利用する接続先。AWS Bedrock、xAI API等。
- **Factory Core**: Task、Workflow、Policy、Approval、Auditを管理する。特定ベンダーのSDKやモデルAPIを直接呼び出さない。

BedrockはCodex / Claude Code等と同じ種類のAgent Runtimeではない。既存Runtimeが内部で利用するモデル接続をFactoryが無理に置き換えることもしない。

## 複雑化を防ぐルール

1. 最初の共通契約は「prompt + workspace → result」に限定する。
2. Runtimeの実行方式はAdapter内に閉じ込める（CLI / SDK / API）。
3. capabilities、resume、streaming、subagents等は、実際に必要になった時点で追加する。
4. 自動モデル選択・自動RuntimeルーティングはMVP対象外。
5. 複数Agentの協調実行やAgent SwarmはMVP対象外。
6. Runtime固有の設定や機能を、無理に共通設定へ押し込まない。
7. Runtimeごとの安全性・権限の違いを明示し、同等だと仮定しない。

## 実装順

1. 最小Agent Runtime契約とCodex CLI Adapter
2. Codexを使った安全なローカルSmoke Test
3. Grok Build CLI Adapterとread-only smoke test
4. 実タスク実行に向けたworkspace / sandbox / approval境界の検証
5. Claude Code Adapter
6. Copilot Adapterの共通契約への接続
7. Gemini CLI Adapter
8. AWS Bedrock / xAI API Model Provider（Custom Agentから直接推論を利用する必要が出た段階）

## 初期契約

Python実装では、最初は同期的な execute(prompt, workspace, timeout) と正規化された RuntimeResult のみを持つ。Coreは製品固有のイベント形式、SDKオブジェクト、CLI引数を知らない。

CodexとGrok Buildの初期Adapterで保証するのは、各CLIをread-only設定で起動し、実行結果・終了コード・session IDを返せることまで。Factory Workflow、永続化、独立レビュー、隔離実行基盤は別の実装段階である。
