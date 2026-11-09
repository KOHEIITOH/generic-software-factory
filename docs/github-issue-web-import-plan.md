# 廃止済み: GitHub Issue Web Import MVP

2026-11-09: 手動取り込み画面・APIは削除しました。現在は[Web実行](local-web-execution.md)でIssueを選択し、実行時に要件を取得・固定します。以下は初期計画の履歴です。

# GitHub Issue Web Import MVP

公開GitHub Issueをプレビューして明示的な操作でFactoryへ取り込む。AI実行やGitHubへの書き込みはしない。

- 入力: owner/repo とIssue番号
- プレビュー: タイトル、本文、元Issue URL
- 取り込み: 既存のFactory.import_external_taskによる冪等登録
- セキュリティ: ローカルAPI、同一オリジン、入力検証、認証情報をUIに表示しない
- 将来: Issue一覧検索、非公開リポジトリ、認証管理
