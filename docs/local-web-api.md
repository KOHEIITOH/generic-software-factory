# ローカルWeb UI / API

既定ではloopback専用のローカル管理画面です。開発依頼の入口はGitHub Issue、実行の記録はRunです。
独立Taskの画面・API・CLI・保存構造は削除済みです。[外部Issueモデル](external-issue-model.md)を参照。
登録済み設定を使う[認証済みWeb実行](local-web-execution.md)を接続しています。

## 起動

```sh
uv run sf web --rebuild
```

初回の依存導入が必要な場合は`uv sync --extra web`を使います。Node.js/npmは初回ビルド・再ビルド時に必要です。
起動したターミナルの操作リンクを開きます。通常のURLは閲覧用です。Dockerは画面の閲覧には不要で、開発実行には必要です。

## 主な読み取りAPI

- `GET /api/health`: 稼働状況。
- `GET /api/integrations`: 既定Providerと認証設定有無。トークン値を返さず認証実確認は行わない。
- `GET /api/runtimes`: 登録名。認証・実行可能性の証明ではない。
- `GET /api/issues`: 保存済み外部Issue参照、Issueごとの直近10 Runと全Run数。
- `GET /api/runs`: 全体の直近Run履歴。

`/guide`、`/onboarding`、`/docs`は説明・API仕様です。

## 既存の変更APIと境界

Project/Repositoryのメタデータ登録はsame-originを要求する既存APIで可能です。
Projectの詳細画面を開くまでは、一覧の取得も登録も行いません。
IssueキャッシュとRunの読み取りAPIは証跡参照用に維持します。通常画面はoperatorのジョブ進捗・履歴を使い、重複した一覧を取得しません。
旧クイック開始、手動取り込み・紐付け、公開GitHub一覧/preview、旧preflight、デモDraft PRの入口は削除しました。
これらのURLは404となり、互換aliasは設けません。Factory内部のIssue取得・紐付け・品質検証・SCM Adapterは維持します。

operator経路は既存の有限Workflowへ接続し、読み取り専用Runtimeを実装実行器へ転用しません。
公開API認証は未実装なので、loopback以外へ公開する運用は対象外です。
完成条件と未接続箇所は[縦断実装チェックリスト](issue-to-pr-vertical-slice.md)を参照してください。

## 認証済みローカルoperator経路

[Web実行操作](local-web-execution.md)はloopback launcherが発行する操作権限を要求する。
`/api/operator/session`、`profiles`、`profiles/{id}/issues`、`profiles/{id}/diagnostics`、
`jobs`、`jobs/{id}/stop`、`logout` を使い、
実行APIは登録IDのみを受け取り、任意path/commandを実行しない。認証済みの初回設定APIだけが明示的なGit rootと検証argvの案を受け取り、固定内容を承認後にprivate設定として保存する。案の作成・登録ではコマンドを実行しない。通常のAPI起動は実行無効。
既存の公開閲覧APIに実行権限は付与しない。operator応答はno-storeとする。


## 認証済み初回設定とHarness提案

`POST /api/operator/setup/inspect` でローカルGit root/origin/Harnessを静的検査し、
`POST /api/operator/setup/proposals` で設定案を保存します。検査中はrepoのコード・テストを実行しません。
静的検査・設定案・登録の422は既知の原因を `detail.code` で返します
（例: `state_overlap`, `worktree_dirty`, `repository_origin`, `execution_image`,
`harness_validation`）。未知の例外は `setup_invalid` とし、例外本文やローカルパスは返しません。
入力スキーマの422は通常の検証エラー形式です。Webは操作段階と許可済みの項目名のみ表示します。
Repository一覧・自動取得の502も `detail.code` で認証未設定、401、アクセス拒否、
404、API利用制限、通信タイムアウト、取得期限、取得上限、応答検証失敗を区別します。
ターミナルには操作名・固定コード・上流HTTPステータスのみを記録します。
例: `Repository acquisition failed: scm_credentials_rejected upstream_status=401`。
トークン、応答本文、URLやRepository名はこのエラー記録には含めません。
SF自身のローカルフォルダを標準の `.sf-factory` 保存先と一緒に使うと
`state_overlap` になります。GitHub選択からの管理領域への取得、または対象外の
`SF_DATA_DIR` を使い、既存データの自動削除・移動は行いません。
`GET /api/operator/setup/proposals` で保存済み案を表示し、
`POST /api/operator/setup/proposals/{id}/approve` で一致するfingerprintと明示確認を要求します。
保存先や認証情報はHTTP入力にしません。旧クイック開始/手動取り込みの公開APIは復活させません。
内部workerの品質失敗からの改善案は同じ保存/承認経路を使います。自動登録・自動再実行はしません。


## 認証済みRepository選択・取得

`GET /api/operator/setup/repositories?cursor=...` が既存GitHub認証でページ単位の選択肢を返します。
`POST /api/operator/setup/acquire` はRepository識別子だけを受け取り、default branchのsourceを検証して
SF管理の場所へ取得し、検査結果を返します。HTTPからURL・clone先・branch・認証情報は指定できません。
同じ認証/host/origin/custom-headerが必要で、匿名の旧`/api/github/repositories`は復活させません。
取得は読み取りと管理baselineの保存だけです。実行権限は従来どおり内容確認後のprofile登録と明示実行で与えます。

Node対応Repositoryのinspect/acquire応答には `node`（静的検証案・manifest/lock fingerprint・
ベースimage・準備済みimage ID）と `checks` を含めます。未対応時は理由を返し、Pythonイメージを
Node向けの既定値として表示しません。
`POST /api/operator/setup/node-image` はroot/repository、正確なfingerprint、`confirmed:true`を要求します。
通常のoperator/session/origin認証の下、固定Dockerfileで明示承認された依存準備のみ行います。
任意Dockerfile・URL・build引数・シークレットは入力できません。準備失敗は422/node_image_build、
版の不一致は409です。登録・AI推論・GitHubへの書き込みはこのAPIでは行いません。
