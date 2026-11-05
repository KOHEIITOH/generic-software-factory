# GitHub IssuesをTaskとして取り込む（Adapter MVP）

`GitHubIssuesSource(repository="owner/repo")` はGitHub REST APIからIssueを読み取る。標準ライブラリのみを使用し、GitHub APIへの書き込みは行わない。

```python
from pathlib import Path
from sf_factory.factory import Factory
from sf_factory.github_issues_source import GitHubIssuesSource
from sf_factory.task_sources import import_issue

factory = Factory(Path(".sf-factory"))
source = GitHubIssuesSource("owner/repo")
task_id = import_issue(factory, source, "42")
print(factory.show_task(task_id))
```

プライベートリポジトリでは、最小権限のトークン（Issues: read）を環境変数等から取得して `token=` に渡す。トークンをソースコードへ埋め込まない。現時点ではCLIコマンドやWeb UIからの取り込みボタンは未実装。

- Issue番号は正の整数に限定し、Pull Requestは拒否する。
- GitHubのタイトル・本文は**信頼できない外部入力**。Factoryに保存しても、AIへの自動実行や権限昇格を意味しない。
- ネットワークエラーでは取り込みに失敗し、Taskを作成しない。
- GitHub.comのみ対応。GitHub Enterprise Serverは今後別設定で扱う。
