# Gemini CLI 0.66.0 — ACP実機検証

このPRは**実機検証用の明示的なコマンド**を追加します。標準Registryには登録せず、通常のFactory実行動作を変更しません。

## Macでの実行

```bash
git fetch origin
git switch feat/gemini-acp-smoke
uv sync --extra dev
uv run python -m sf_factory.gemini_acp_smoke
```

期待する出力は `"status": "succeeded"` と `GEMINI_ACP_OK` です。失敗した場合は出力の `status`、`error_kind`、`error_message` を共有してください。認証情報・秘密鍵・環境変数・プロンプト履歴は共有しないでください。

## 安全性と制限

- 実行前に `gemini --version` と `gemini --help` の `--acp` 対応を確認してください。
- コマンドは使い捨てのディレクトリを作成し、`--approval-mode plan` で読み取り専用の応答を要求します。
- **一時ディレクトリはセキュリティサンドボックスではありません**。GeminiプロセスにはMacユーザーと同じファイル・ネットワーク権限が残ります。
- 業務情報、機密データ、アクセスキーを含む環境では実行しないでください。OS隔離やコンテナ隔離は別途必要です。
- 現時点では実機検証未実施です。CIはモックを使ったオフライン検証のみ行います。
- `AcpRuntime` の初期実装は基本的なACPメッセージのみ対応しています。Gemini固有の通知・権限交渉が必要な場合、検証結果を踏まえて追加します。
