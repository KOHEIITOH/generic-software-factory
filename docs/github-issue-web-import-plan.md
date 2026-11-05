# GitHub Issue Web Import MVP

公開GitHub Issueをプレビューして明示的な操作でFactoryへ取り込む。AI実行やGitHubへの書き込みはしない。

- 入力: owner/repo とIssue番号
- プレビュー: タイトル、本文、元Issue URL
- 取り込み: 既存のFactory.import_external_taskによる冪等登録
- セキュリティ: ローカルAPI、同一オリジン、入力検証、認証情報をUIに表示しない
- 将来: Issue一覧検索、非公開リポジトリ、認証管理
