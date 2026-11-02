# セキュリティ基準

Software Factoryはコードを実行し、Agentに操作を委任します。タスク入力、リポジトリの内容、コメント、ツール出力、モデル出力は信頼できないものとして扱います。

## 必須の制御

- 信頼できないコードには分離実行を必須とする。
- Secret Managerまたは環境変数参照を使い、実行時に認証情報を注入する。
- タスクとAdapterごとに最小権限を適用する。
- ネットワークへの外向き通信は既定で制限する。
- ホストの認証情報、SSH Agent、Docker Socket、無関係なディレクトリをSandboxにマウントしない。
- ログと成果物からSecretをマスキングする。
- 時間、メモリ、CPU、Token／コストの予算を適用する。
- マージ、デプロイ、破壊的操作、Policy変更には人の承認を必須とする。
- 特権操作ごとに監査イベントを記録する。
- Adapterの依存関係を固定し、レビューする。

## Prompt Injectionと信頼できないコンテンツ

リポジトリのファイル、Issueの説明、コメント、ツール出力には、Policyを上書きしようとする指示が含まれる場合があります。それらはデータであり、権限を持ちません。システムPolicyと権限チェックは、Agentのpromptの外側で適用します。

## 自己改善の境界

Factoryは実行結果を分析し、prompt、Workflow、Adapter、Coreの改善を提案できます。セキュリティPolicy、権限、Coreの実行ロジックへの変更を、黙って適用してはいけません。変更にはレビュー、テスト、バージョン付きリリースが必要です。

## ローカルリポジトリの読み取り専用解析

`sf analyze` は利用者が明示したGitリポジトリrootだけを走査し、対象ファイルを制限したsnapshotとしてCopilotへ送信します。送信前に `--confirm-send` が必要です。隠し・生成物directory、symlink、unsupported / binary file、名前から機密の可能性があるfileを除外し、件数・深さ・byte数に上限を設けます。実際に含めたfile、除外数、上限到達は解析結果に表示し、FactoryのTask/Run/Audit DBにはソース内容を保存しません。

ファイル名の除外はsecret検出ではなく、コードや設定内の秘密情報を完全には防げません。利用者は送信先の利用規程を確認してください。Copilot SDKのtool allowlistは空ですが、OS-level process isolationではありません。この機能はソース編集、shell実行、PR作成、隔離保証を提供しません。
