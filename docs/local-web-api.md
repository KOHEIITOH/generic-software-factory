# ローカルWeb UI / API

既定ではloopback専用のローカル管理画面です。開発依頼の入口はGitHub Issue、実行の記録はRunです。
独立Taskの画面・API・CLI・保存構造は削除済みです。[外部Issueモデル](external-issue-model.md)を参照。
閲覧・Issue取込に加え、登録済み設定を使う[認証済みWeb実行](local-web-execution.md)を接続しています。

## 起動

```sh
uv run sf web --rebuild
```

初回の依存導入が必要な場合は`uv sync --extra web`を使います。Node.js/npmは初回ビルド・再ビルド時に必要です。
URLは`http://127.0.0.1:8000/`です。Dockerは閲覧・取込には不要です。

## 主な読み取りAPI

- `GET /api/health`: 稼働状況。
- `GET /api/integrations`: 既定Providerと認証設定有無。トークン値を返さず認証実確認は行わない。
- `GET /api/runtimes`: 登録名。認証・実行可能性の証明ではない。
- `GET /api/issues`: 保存済み外部Issue参照、Issueごとの直近10 Runと全Run数。
- `GET /api/runs`: 全体の直近Run履歴。
- `GET /api/github/repositories`、`/api/github/issues`、`/api/github/issue`: 既存GitHub Adapterの取得/プレビュー。
- `GET /api/issues/{issue_key}/implementation-preflight`: 変更や実行を開始しない事前チェック。

`/guide`、`/onboarding`、`/docs`は説明・API仕様です。

## 既存の変更APIと境界

Project/Repository登録、Issue取込、検証済みRepositoryとの関連付けは既存APIで可能です。独自Task作成は削除済みです。
ブラウザの変更要求はsame-originを要求します。GitHub Draft PRデモは明示boolean確認と権限検査後に
markerだけを追加する機能であり、Issueの実装や自動配送ではありません。

operator経路は既存の有限Workflowへ接続し、読み取り専用Runtimeを実装実行器へ転用しません。
公開API認証は未実装なので、loopback以外へ公開する運用は対象外です。
完成条件と未接続箇所は[縦断実装チェックリスト](issue-to-pr-vertical-slice.md)を参照してください。

## 認証済みローカルoperator経路

[Web実行操作](local-web-execution.md)はloopback launcherが発行する操作権限を要求する。
`/api/operator/session`、`profiles`、`jobs`、`jobs/{id}/stop`、`logout` を使い、
HTTPから設定ファイルpathや任意commandを受け取らない。通常のAPI起動は実行無効。
既存の公開閲覧APIに実行権限は付与しない。operator応答はno-storeとする。
