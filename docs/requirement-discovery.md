# 要件ファイルを指定しても、省略しても計画する

親Issueを指定した既存の `sf issue plan` / `sf issue advance` と、Webの
「計画・子Issueを作成」「次の1ステップを実行・再開」で利用できます。
要件ファイルの検出に追加のAI Agentや設定サービスは不要です。

## 明示指定を優先

実行設定に `context_paths` があれば、その参照だけを使い、自動で他の資料を足しません。
既存のコード/テスト参照も同じ扱いです。

```json
"context_paths": ["docs/requirements.md", "docs/architecture.md"]
```

指定した資料が存在しない・不正な場合、自動検出で代用せず停止します。
`context_hashes` を指定する場合は、context_paths内のSHA256に制約を追加できます。
通常は計画時に検出した内容が後続の子Issue用に自動固定されるため、手入力は不要です。

## 指定を省略して自動検出

`context_paths` を省略するか `[]` にすると、検証済みGit revisionの候補を探します。

- ルートのREADME（拡張子なし、日本語版などの名前も含む）
- ルートの要件・仕様・PRD・設計・アーキテクチャ文書
- `docs/`、`doc/`、`documentation/`、`requirements/`、`spec/`等の要件・仕様・設計候補
- Markdown（`.md`/`.markdown`）、`.rst`、`.txt` のUTF-8テキスト

例：`README.md`、`docs/requirements.md`、`docs/要件定義.md`、
`docs/specifications/payment.md`、`docs/architecture.md`。
ADR/decisions・archive/history・test/fixtures・vendor・生成物は除外します。
一般のインストール説明を含む全docsや、リンク先を無制限に読む機能ではありません。
非標準の資料はcontext_pathsで指定してください。ルートの`requirements.txt`は
依存パッケージ一覧と区別するため自動候補にしません。

候補がなければ親Issueの要件を使います。親Issueにも十分な要件がない場合は、
内容を創作せず不足として停止します。repoだけから親Issueを作成する入口は対象外です。

## 解釈・タスク分割と根拠

計画AIは各要件に「親Issueまたは参照ファイル」の出典を付け、完遂可能な子Issue、
受入条件、既存check ID、変更可能なパス、依存関係へ分解します。
独立したレビュー呼出しが、各資料の役割・要件の十分さ・矛盾・出典・計画を確認します。
不足・未解決の矛盾・未知の資料の引用・レビュー不備では、子IssueやPRを作成しません。
これはAIによる判断であり、矛盾を機械的に完全証明するものではありません。

Webでは実行前に「明示指定／自動検出」を表示し、実行後に「参照した要件資料・分割の根拠」で
パス・選択理由・ハッシュ・版・判定カテゴリ・要件ID→出典→子Issueの対応を確認できます。
詳細な解釈・指摘は `SF_DATA_DIR/automation-v1/<session_id>/state.json` の
`requirement_sources` と `planning_review` に保存します。本文・解釈の生テキストはHTTPへ返しません。

子Issueの実装・独立レビュー・同じPRの修正にも同じ参照とハッシュを渡します。
計画後に資料が変更・削除されれば、推論/配送を進めず理由を残して停止します。
参照資料は読み取り専用です。資料自体を変更する場合は別の計画・スコープとして扱います。
既存の凍結済み計画は再検出しません。journalを消して再送や予算リセットを強制しないでください。

## 上限

最大12資料、各24 KiB、資料合計48 KiB。Harnessと合計32参照、既存の計画context 64 KiB
（JSON表現）、モデルcontext/推論回数/token/API/期限の上限も維持します。
超過時は黙って切り詰めず停止するため、必要な資料を明示・縮小してください。
候補は読み取りデータであり、Harnessのルール、許可command、認証、変更可能パスを増やしません。

検証は模擬AI/SCM＋実保存・実Docker・実ブラウザで行います。
Bedrock/GitHubの実サービス最終通しは引き続きPCで確認します。

Webの新規計画は[計画確認と承認](local-web-execution.md)を経て子Issueを作成します。
承認前に解釈・受入条件・依存関係を確認でき、承認だけではAIを呼びません。
