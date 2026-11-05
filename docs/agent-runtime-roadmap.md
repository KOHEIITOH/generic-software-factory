# Agent Runtime / Model Provider 対応方針

## 目的

主要なCoding Agentを選べるようにしつつ、Factory Coreを複雑にしすぎない。最初から全製品・全モデルの組み合わせを抽象化するのではなく、実際に使うRuntimeを順番に追加する。

## 標準対応の対象

| 対象 | 分類 | 方針 | 状態 |
|---|---|---|---|
| OpenAI Codex CLI | Agent Runtime | 最初の実装・ローカル実証対象 | Read-only Adapter |
| Grok Build CLI (xAI) | Agent Runtime | headless CLI経由。ACPは必要になった段階で検討 | Read-only Adapter |
| Claude Code | Agent Runtime | 次のRuntime候補 | Planned |
| GitHub Copilot SDK | Agent Runtime | 共通契約へ接続。空workspace・ツール無効で実行 | SDK Adapter |
| Gemini CLI | Agent Runtime | 次段階で追加 | Planned |
| AWS Bedrock | Model Provider | Converse APIでテキスト推論。Custom Agent連携は別段階 | Inference Adapter |
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
6. Copilot SDK Adapterの共通契約への接続
7. Gemini CLI Adapter
8. AWS Bedrock / xAI API Model Provider（Custom Agentから直接推論を利用する必要が出た段階）

## 初期契約

Python実装では、最初は同期的な execute(prompt, workspace, timeout) と正規化された RuntimeResult のみを持つ。Coreは製品固有のイベント形式、SDKオブジェクト、CLI引数を知らない。

CodexとGrok BuildのAdapterで保証するのは、各CLIを既定のread-only設定で起動し、実行結果・終了コード・session IDを返せることまで。Copilot SDK AdapterはローカルCopilot認証を利用し、空workspaceで利用可能ツールを無効にして応答を得る。これはCodex/Grokと同等のsandboxやOSレベルの隔離を保証せず、現在のFactory run workspaceにも対象リポジトリは取り込まれない。Factory Workflow、永続化、独立レビュー、隔離実行基盤は別の実装段階である。

## AWS Bedrock Model Provider（推論専用）

`pip install -e '.[bedrock]'` で任意依存の boto3 を導入する。
AWS認証はboto3標準のcredential chain（環境変数、AWS profile、IAM Role等）を利用し、
アクセスキーをFactory設定やGitに保存しない。利用リージョン、モデルID、Bedrockのモデル利用権限、
IAMの `bedrock:InvokeModel` 権限等をAWS側で用意する必要がある。

```python
from sf_factory.bedrock_provider import BedrockModelProvider

provider = BedrockModelProvider(
    model_id="YOUR_BEDROCK_MODEL_ID",
    region_name="ap-northeast-1",
)
response = provider.generate("こんにちは")
print(response.text)
```

このアダプターは `ModelProvider` 契約でテキスト推論するだけで、`AgentRuntime`
への登録、ファイル編集、ツール実行、Taskの自律実行はまだ提供しない。
AWS実環境での接続確認には利用者のAWS権限・モデルIDが必要。

## Bedrock設定のローカル診断

`SF_BEDROCK_MODEL_ID` にモデルID、`SF_BEDROCK_REGION` にリージョンを設定する。
リージョンは `AWS_REGION` / `AWS_DEFAULT_REGION` でも指定可能。
`sf provider list` はこれらの設定と任意依存 `boto3` の存在のみを表示する。
AWSに通信せず、認証・IAM権限・モデル利用可否・推論成功は確認しない。
資格情報をコマンド出力やリポジトリへ保存しないこと。

## Bedrock実接続のSmoke Test（明示実行）

AWS側でモデル利用権限と `bedrock:InvokeModel` を準備し、
ローカルで `pip install -e '.[bedrock]'` を実行する。
AWS標準のprofile / IAM Role等で認証した上で、
`SF_BEDROCK_MODEL_ID` と `SF_BEDROCK_REGION` を設定する。

```bash
sf provider list
sf bedrock-smoke --confirm-invoke
```

Smoke Testは実際にBedrockへ短いプロンプトを1回送信し、**AWS利用料金が発生し得る**。
`--confirm-invoke` なしでは実行しない。認証情報やプロンプト本文は出力しない。
Factory Taskの自動実行やファイル編集は行わない。
