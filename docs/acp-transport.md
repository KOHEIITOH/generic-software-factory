# ACP共通接続 — 実験的Transport

この実装は**ACP（Agent Client Protocol）のstdio JSON-RPC通信を行う最小PoC**です。既存のCodex / Grok / Copilot Adapterを変更せず、共通の `AgentRuntime.execute` 契約を実装します。

## 対応範囲

- `initialize` → `session/new` → `session/prompt` の基本シーケンス
- `session/update` のテキスト断片を結果へ正規化
- timeout / 不正応答 / プロセス起動失敗を安全なエラーへ正規化
- Factoryへのツール・権限要求は承認しない

## 重要な制限

**Gemini CLI・Claude Codeとの実機互換性はまだ未確認です。** ACPの基本通信のみをFake Agentでテストしています。実際のACP Agentは自分の権限でローカルファイル・コマンド・ネットワークにアクセスできる可能性があります。FactoryがACP要求を拒否してもOS隔離にはなりません。

このため、`AcpRuntime` は**デフォルトRegistryやCLIには登録していません**。実機検証は隔離コンテナ、使い捨ての非機密workspace、最小権限・ネットワーク制限を備えてから実施してください。

次のPRでOS隔離と権限境界を検証したうえで、Gemini CLIを対象に `gemini --acp` の接続確認と、設定によるRuntime登録を追加する予定です。Claude CodeはACP Bridgeの必要性を個別確認します。

## テスト

```text
uv run pytest tests/test_acp.py
```

テストはPythonで書いた偽のACP Agentのみを起動します。外部AIへの接続や課金はありません。
