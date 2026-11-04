# Software Factory ローカル管理画面

React + TypeScript と FastAPI のローカル管理画面です。GitHub Pagesへの公開は不要です。

## 普段の起動（ワンコマンド）

初回のみ Python 依存関係をセットアップします。

```bash
uv sync --extra web
```

その後はリポジトリ直下で以下を実行します。

```bash
uv run sf web
```

初回起動時だけ Node.js/npm を使ってフロントエンドをインストール・ビルドします。2回目以降はビルド済みファイルをFastAPIから直接配信するため、Node.jsの開発サーバーは不要です。ブラウザは http://127.0.0.1:8000 で開きます。画面を更新したい場合は `uv run sf web --rebuild` を使います。

開発中にホットリロードが必要なら従来通りFastAPIと `cd web && npm run dev` を別々に起動できます。

現段階は読み取り専用です。Runtimeの「登録済み」はローカルインストールや認証の成功を意味しません。タスク実行・マージ機能はまだありません。サーバーは127.0.0.1のみで起動します。
