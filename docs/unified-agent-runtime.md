# 統一 Agent Runtime 接続層

## 目標

Factory CoreはAI製品名を知らず、**1つのAgentRuntime契約**を通してAIへ作業を委譲します。新しいAIを追加してもTask / Run / Auditのコードに製品別分岐を増やさないことが目的です。

## 今回実装した範囲

- `AgentRuntimeRegistry` に名前と生成関数を登録する
- `Factory.run_task` はRegistryからAdapterを取得する
- Codex / Grok Build / Copilot SDKは従来の実装・制約を保ってRegistryに登録する
- Custom Agentも `AgentRuntime.execute(prompt, workspace, timeout_seconds)` を満たすクラスを登録できる
- Registryは**接続先の選択機構**であり、通信プロトコルの自動変換ではない

```python
from pathlib import Path
from sf_factory.agent_registry import AgentRuntimeRegistry
from sf_factory.factory import Factory

registry = AgentRuntimeRegistry()
registry.register("my-agent", MyAgentRuntime)  # AgentRuntime契約を満たす実装
factory = Factory(Path(".sf-factory"), runtime_registry=registry)
```

上の例では `MyAgentRuntime` の実装・importを利用者側で用意します。CLIから設定ファイルを読み込んで任意のCustom Agentを登録する機能はまだありません。

## 次の段階

1. **ACP transport Adapter**を独立して追加し、ACP対応Runtimeを設定で選べるようにする。まずGemini CLIで実証する
2. Claude Codeは公式に利用できる接続方式と安全な権限制御を確認してから接続する。ACP非対応の部分は薄いBridgeが必要な可能性がある
3. Custom AgentはACP Serverとして接続する方法と、Python AgentRuntimeを直接登録する方法を用意する
4. 実行Adapterの権限・隔離・タイムアウト・監査を独立して強化する

**1つの共通窓口 ≠ 1つの万能な実行実装**。CLI/SDK/ACPの差はTransport層に閉じ込めます。ACPに対応していない既存Runtimeを無理にACPへ置き換えません。

## 安全性

RegistryはPolicyやOS sandboxを代替しません。未知のCustom Agentは任意コードを実行し得るため、**信頼できないAdapterを登録しない**でください。既存Factoryのread-only Policyと空workspaceを維持しますが、プロセス隔離やネットワーク遮断の保証はありません。
