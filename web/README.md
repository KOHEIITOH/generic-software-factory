# Software Factory ローカル管理画面

このReact + TypeScript画面はローカルのFastAPIを参照します。GitHub Pages公開は不要です。

## 起動

ターミナル1（リポジトリのルート）:

```bash
uv sync --extra web
uv run --extra web uvicorn sf_factory.web_api:app --host 127.0.0.1 --port 8000
```

ターミナル2:

```bash
cd web
npm install
npm run dev
```

ブラウザで http://127.0.0.1:5173 を開きます。

現段階は読み取り専用です。Runtimeの「登録済み」はローカルインストールや認証の成功を意味しません。タスク実行・マージ機能はまだありません。

Viteの開発サーバーが `/api` をlocalhost:8000に転送します。両サーバーともローカル専用で起動し、外部公開しないでください。
