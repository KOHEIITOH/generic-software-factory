# GitHubを初期標準にする方針と対応状況

この文書の完了範囲は「GitHubを初期標準として維持し、Core/共通Workflowから固有依存を分離する」です。
Issue→AI実装→テスト収集→Draft PRの自律実行やM3全体の完了を意味しません。

## 利用開始

通常の起動はこれまでどおりです。

```sh
uv run sf web --rebuild
```

- Task SourceとSourceControlはGitHubを既定とし、Provider選択の追加設定は不要。
- ProjectへのRepository登録もGitHubを初期選択にし、Local Gitも引き続き選択可能。
  登録だけで権限や実行許可を付与せず、この登録はメタデータです。
- GitHub Repository一覧・非公開Issue・PR操作には、サーバー側の`GH_TOKEN`または`GITHUB_TOKEN`が必要。
  両方ある場合は`GH_TOKEN`優先。公開Issueの匿名読取は維持。
- 対象Repositoryを自動で書込先に決めない。デモの変更操作はsame-origin JSONと明示boolean確認、
  書込/PR capability確認後にだけ実行し、Draft PRのみを作る。Mergeは追加していない。
- 起動・設定確認だけではGitHub APIやAIを呼び出さない。

任意の読み取り専用診断は`uv run sf integration show`または`GET /api/integrations`です。
Provider名、認証用環境変数名、設定有無を返します。トークンは出力しません。
`authenticated: not_checked`は、設定済みでもGitHub認証や権限を実確認していないことを示します。

`config/factory.example.yaml`はGitHubを標準とする将来の設定例です。現行CLI/WebにYAML loaderを
追加した変更ではありません。実際の選択は`integration_defaults.py`の組立と各入口で行います。

## 完了条件と根拠

| 条件 | 状態・根拠 |
| --- | --- |
| GitHub Issuesを初期標準として維持 | 既存`TaskSourceAdapter` / `ExternalIssue`を再利用し、既定factoryをGitHubへ接続。Webの取得/取込/一覧を維持 |
| CoreのGitHub固有検証を除去 | PR #97。`RepositoryBindingAdapter`に注入し、origin/provider/case規則を`GitHubRepositoryBinding`へ移動 |
| 共通WorkflowにAPI/認証型を持ち込まない | `SourceControl`、`RepositoryCapabilities`、`PullRequestReference`を使用。Core/shared Workflowのimport guardで保護 |
| 既存Draft PR動作をAdapter経由にする | PR #98。`GitHubSourceControl`にREST/認証/JSONを閉じ込め、既存の確認済みデモを共通処理へ接続 |
| 最小設定でGitHubを選択 | `integration_defaults`、Web初期値、既存2種類の認証環境変数、設定例を一致させた |
| 他サービスを実装しない | GitLab/Bitbucket/Jira等の新規Adapterなし。契約検証にfixtureのみ使用 |
| 既存データ・起動・安全境界を維持 | SQLite/File、GitHub HTTPS/SSH照合、Issue同一性、匿名読取、確認/権限拒否の回帰テスト |

## 境界

- `factory.py` / `file_dashboard.py`: 共通契約で検証し、保存だけを行う。
- `workflow.py` / `workflow_runner.py` / `draft_pr_demo.py`: 共通ドメイン型と操作を使う。
- `integration_defaults.py`: 初期Providerを選ぶ組立箇所。GitHub選択をここへ集約する。
- `github_*`: GitHubのURL/API形式・認証・origin照合と専用HTTP入口。

Repositoryの既存契約を優先し、SourceControlは現在使う操作だけを追加した。将来Adapterが増えても
Coreの処理を書き換えず、組立とAdapter側で接続することを目標とする。汎用plugin registryや他サービスの
設定項目を先回りして追加していない。

## 検証と残る範囲

実Gitのorigin照合、GitHub固有の大文字小文字規則、SQLite/Fileの保存、fixtureのcase-sensitive識別子と
opaque SCM識別子、確認/権限拒否、REST変換、秘密非表示、Core import guardをテストする。
GitHub連携の変更系APIはmockで検証し、試験目的のBranch/Issue/PRを実サービスへ自動作成しない。

既存デモのbranch/file/PRは複数資源の操作であり、分散transactionやexactly-onceではない。
途中失敗・結果不明時の自動再試行や削除は追加していない。実装成果物からの安全な配送、
外部結果の照合・冪等性、Worker復旧、公開API認証は引き続き別の実装項目。
