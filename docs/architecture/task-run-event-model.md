# Task / Run / Trigger 設計メモ

参考: https://qiita.com/Syoitu/items/9364a0a175893bb15219 （2026-11-04）

- **Task**: 人間が依頼する仕事。複数回実行できる永続データ。
- **Run**: 1つのTaskを1回実行した記録。実行ごとに状態・結果・ログを保持。
- **Trigger**: CLI、Web UI、Issue更新、スケジュールなどの起動イベント。将来的にAdapterとして扱う。
- **Runner**: 実行環境。ローカル・Docker・クラウドの実装を交換可能にする。
- **Orchestrator**: Runの状態遷移と品質ゲートを制御し、外部のPR承認待ちにプロセスを占有させない。

## 今回の実装範囲

ローカルSQLiteのTaskとRunを読み取り専用APIで参照し、ダッシュボードに表示する。タスク作成・実行、ポーリング、PR承認、自動マージは今回追加しない。外部からのコード実行を可能にする前に認証、CSRF対策、隔離、権限境界を設計する。

記事のGitHub Actions構成は参考例であり、Factory Coreの必須依存にはしない。
