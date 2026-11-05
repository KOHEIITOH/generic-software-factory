# ローカルWeb UI / API（実験的MVP）

現在のWeb UIはReact/TypeScript/Viteで実装済みです。**閲覧専用**であり、WebからAIを実行したりIssueを取り込んだりする操作はまだありません。

## 起動

```bash
uv sync --extra web
uv run sf web --rebuild
```

Node.js/npmが初回ビルドまたは再ビルド時に必要です。ブラウザで http://127.0.0.1:8000/ を開きます。

## 画面

- `/`: ダッシュボード（登録済みRuntime、Task、Runを閲覧）
- `/guide`: ユーザーガイドHTML
- `/onboarding`: オンボーディングHTML
- `/docs`: FastAPIのAPI仕様

## 読み取り専用API

- `GET /api/health`: APIの稼働状況
- `GET /api/runtimes`: 登録済みRuntime名（認証・実行可能性を保証しない）
- `GET /api/tasks`: 保存済みTask一覧
- `GET /api/runs`: 保存済みRun一覧

タスクやRunの作成・実行・削除を行うHTTPエンドポイントはありません。GitHub Issues AdapterはPython APIで利用できますが、Web UIのIssue取り込み機能は未実装です。

## 安全上の注意

認証は未実装です。ローカル専用（127.0.0.1）で起動し、`0.0.0.0`で公開したりインターネットに接続したりしないでください。DockerはWeb UI閲覧には不要です。任意リポジトリでの自律開発・隔離実行・PR自動作成は今後の課題です。
