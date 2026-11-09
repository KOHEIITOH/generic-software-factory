# GitHub Issuesを外部参照として取り込む

`GitHubIssuesSource(repository="owner/repo")` はGitHub REST APIからIssueを読み取る。標準ライブラリのみを使用し、GitHub APIへの書き込みは行わない。

```python
from pathlib import Path
from sf_factory.factory import Factory
from sf_factory.github_issues_source import GitHubIssuesSource
from sf_factory.task_sources import import_issue

factory = Factory(Path(".sf-factory"))
source = GitHubIssuesSource("owner/repo")
issue_key = import_issue(factory, source, "42")
print(factory.show_issue(issue_key))
```

プライベートリポジトリでは、最小権限のトークン（Issues: read）を環境変数等から取得して `token=` に渡す。トークンをソースコードへ埋め込まない。認証済みWebとローカル開発CLIが実行時に利用する。手動取り込みのWeb入口は削除済み。通常の利用者による上記Python APIの操作は不要。

- Issue番号は正の整数に限定し、Pull Requestは拒否する。
- GitHubのタイトル・本文は**信頼できない外部入力**。Factoryに保存しても、AIへの自動実行や権限昇格を意味しない。
- ネットワークエラーでは取り込みに失敗し、Issueキャッシュを更新しない。
- GitHub.comのみ対応。GitHub Enterprise Serverは今後別設定で扱う。

独立Taskは削除済み。[外部Issueモデル](../external-issue-model.md)を参照。
