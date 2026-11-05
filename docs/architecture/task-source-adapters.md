# 外部Task連携の基本方針

FactoryはJira・GitHub Issues・Backlog等のチケット管理を置き換えない。Factory Coreは実行単位としてTask/Runを保持し、外部Issueとの紐付けをSource Adapterが担う。

## 不変条件

- 外部Issueの識別子は `provider + instance + external_id` の組み合わせ。異なるテナントやサービス間で衝突しない。
- 同一Issueを何度取得してもFactory Taskは重複しない。
- 初回取り込み後のTask promptは再取り込みでは書き換えない。更新ポリシー・差分レビューは後続PRで明示する。
- 外部Issueの状態とFactory Runの状態は別物。
- CLIのローカルTask作成は従来通り動作する。
- 外部へのコメント投稿・ステータス変更・Webhook受信・AI実行は今回の範囲外。

## 次の段階

1. Adapter Protocolと手動取り込みCLIを追加し、実プロバイダを接続する前に契約を固定する。
2. 認証情報の保管とAPI権限の最小化、外部入力の信頼境界、同期失敗時のリトライを設計する。
3. Web UIには元IssueへのリンクとRunの実行状況を表示する。タスク管理の二重化を避ける。
4. 外部更新・PRコメントは明示的な設定と権限確認後に追加する。
