# 要件分割・レビュー修正・Harnessの利用

PCのDockerとBedrock認証を使うローカルCLIの経路です。Webは従来どおり
`uv run sf web --rebuild` で起動し、[Web実行操作](local-web-execution.md)からも
同じWorkflowを進められます。実サービスの最終通し確認はPCで行います。

## 準備

[ローカルIssue開発](local-issue-development.md)と同じoperator設定、GitHub権限、
固定digestの実行image、ネットワークなしで動く承認済み挙動チェックを使います。
`issue` は要件が書かれた親Issueです。Coreの独自Task登録はありません。
GitHub認証にはIssue作成・子Issue関連付け・Repository/PR操作の権限が必要です。

共有ルールを使う場合は設定に `project_harness_file` を追加します。
共有ファイルは対象repoの外に置き、operator所有・他者書込不可にします。

```json
{"project":"payments","rules":[{"name":"quality","text":"公開APIと承認済みチェックを維持する"}]}
```

Project共通ルール、RepositoryのAGENTS/Harness、変更対象directoryのAGENTSを
同じbundleへ固定し、実装・独立レビューへ渡します。各repoには既存の明示選択
または理由付き除外が必要です。どの層も権限・commandを追加できません。

## 計画と実行

```sh
uv run sf issue plan --config /outside/repo/operator.json --confirm-run --confirm-bedrock
uv run sf issue advance --config /outside/repo/operator.json --confirm-run --confirm-bedrock
```

`plan` は既存source/Harness、要件、承認済み検証を読み、独立レビューを通した
最大8単位の計画をGitHubネイティブ子Issueとして保存します。各単位には
要件ID、目的、受入条件、変更可能なパス、既存のcheck ID、依存関係があります。
循環・参照欠落・未カバー要件/チェック・権限拡張は拒否します。再分割はしません。
1単位の場合も親要件を保存したまま子Issueへ実行範囲を分離します。

`advance` は計画がなければ作り、実行可能な子Issueを1つだけ実装してDraft PRへ
進めます。既にPRがあればレビュー修正またはマージ状態の確認を1ステップ進めます。
次の子Issueを始めるには、先のPRの正確なheadが実際にmergedである証拠が必要です。
Issueのcloseやレビュー承認だけでは依存関係を解除しません。人間のmerge後、
同じ `advance` を再実行します。次の単位は最新default branchの検証済みsourceを
使うため、各mergeの後でhostを自動checkoutしません。

## 単独PRのレビュー修正

```sh
uv run sf issue review --config /outside/repo/operator.json --run ORIGINAL_RUN_ID \
  --confirm-run --confirm-bedrock --reviewer REVIEWER_LOGIN
```

`--reviewer` は複数指定できます。省略時は認証operatorのloginだけを信頼します。
installation tokenなど `/user` を読めない認証では明示指定します。元のFactory製PRに
対し、指摘→実装→実Dockerの挙動検証→独立レビュー→同じbranchへのCAS追記を行います。
人間のthreadを勝手に解決したり、ready/merge/release操作をしたりしません。

## 有限性と復旧

1回のコマンドは最大1つの実装/修正ラウンドまたは状態確認で終了します。
同じ設定・data rootで再実行しても、累積上限をリセットしません。

| 上限 | 単独PR修正 | 要件ワークフロー全体 |
| --- | --- | --- |
| 修正ラウンド | PRごとに3 | 各PR3、全体の推論上限も適用 |
| 推論呼出し | 8 | 32（計画・全子Issue・修正の合計） |
| 保守的な予約token | 3,000,000 | 6,000,000 |
| API呼出し | 2,500 | 2,500 |
| 論理write action | 128 | 128 |
| 期限 | 7日 | 7日 |
| 子Issue / 分割深さ | 対象外 | 8 / 1 |

token予約はSDK再試行と最大出力を保守的に含みます。通貨料金の保証ではありません。
承認待ち・マージ待ちは `waiting` として保存して終了し、polling loopは作りません。
品質失敗、同一候補、予算切れ、要件編集、外部head/base変更、Harness/manifest変更は
理由を記録して停止します。モデルやcommit準備の結果不明は再送しません。
Issue作成・関連付け・branch更新の結果不明はreadbackだけで照合し、不在でも
再作成しません。保存先やjournalを消して再送を強制しないでください。

判断の証跡は `SF_DATA_DIR/automation-v1/<session_id>/state.json` の `decisions`、
実装根拠は既存Run・source snapshot・check/review evidenceに保存します。
CLI出力のreasonとsession_idから確認できます。通常の設計判断で追加質問はしません。

## 要件資料の自動検出

`context_paths` を指定すれば優先し、省略/空ならREADME・要件/仕様文書の候補を探します。
不足・矛盾を検知した場合は子Issue作成前に停止し、出典・解釈・分割の根拠を保存します。
上限と根拠の確認方法は[要件資料の検出](requirement-discovery.md)を参照してください。
