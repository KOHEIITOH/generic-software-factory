# PCでIssue → AI実装 → 隔離テスト → 独立レビュー → Draft PRを試す

## 対象と境界

ローカルOSのoperatorが、対象repository外に保存した設定を明示して起動するCLI。
同じ開発処理は[Web実行と初回設定](local-web-execution.md)からも利用できる。本書はCLIで設定する場合の詳細。
この経路はGitHubを標準Adapterに使うが、共通controllerはTaskSource/SourceControl契約で動く。
DBは不要。新しいIssue形式のSQLiteは保持し、新しいPOSIX rootはFileを使用する。
旧Task形式のrootはサポートしないため、[新しい保存先](external-issue-model.md)でIssueを取り込み直す。

ここでのBedrock呼出しは**PCで明示実行すると課金が発生し得る**。この開発環境では
実Bedrock/実GitHub配送の通し成功を確認していない。CIの縦断テストは実Git/File/Dockerを
使い、AIとSCMサービスはfixture。実サービスでの確認は以下を使ってPCで行う。

## 前提

- クリーンなローカルGit checkout。HEADをremote default branchと同じcommitにする。
  SF自身を対象にする場合も、uv/npmの自動生成lockとegg-infoはこのrepositoryのignore対象。
  target側の実ソースの変更や、未追跡の作業ファイルはcommit/stash等で整理してから実行する。
- 正式なGitHub Issueと、repositoryへのbranch/PR書込権限。
- local Docker socket、CPU/memory/PID制限が実際に有効なdaemon。
- digestで固定した信頼するPython入りimageを、operatorが事前にpull済みであること。
- 選択したHarnessを検証/構成できること。未解決のprofile例は明示的に除外する。
- AWS標準認証と、指定モデルへのBedrock Converse権限。認証情報は設定JSONへ書かない。

一度だけ依存を準備する。

```sh
uv sync --extra dev --extra web --extra bedrock
```

PCのshellでAWSプロファイル、モデルIDとregionを設定する。AWS_ACCESS_KEY等をコードや
imageへ書き込まない。SSOを使う場合はPC上で対象profileのloginを完了しておく。

```sh
export AWS_PROFILE=your-profile
export SF_BEDROCK_MODEL_ID=your-converse-model-or-inference-profile-id
export SF_BEDROCK_REGION=ap-northeast-1
# 必要な場合だけ。選択したモデルが許すoutput token上限に合わせる（最大32768）。
export SF_BEDROCK_MAX_TOKENS=8192
export GH_TOKEN="$(gh auth token)"
```

## operator設定

設定はrepository**外**の絶対pathに保存し、自分が所有して他ユーザーから書込不可にする。root/data_rootは重ならない別の場所を使う。
設定は任意commandをAIに選ばせず、変更path、Harness、参照path、実テストargvと期待stdoutを
推論前に固定する。以下は、小さなcalculator repositoryに正式Issueがある場合の例。
owner/repo、Issue、path、Harness、imageは自分の対象に合わせて編集する。

```json
{
  "repository": "OWNER/REPOSITORY",
  "issue": "123",
  "root": "/absolute/path/to/clean-repository",
  "data_root": "/absolute/path/to/private-factory-state",
  "provider": "bedrock",
  "image": "python@sha256:09a17cad02668ae61ece136b4fd36ac3849e14f670ebedb637ea3e15580525bc",
  "allowed_paths": ["calculator.py"],
  "selected_harness": ["AGENTS.md"],
  "context_paths": ["test_calculator.py"],
  "excluded_harness": [],
  "checks": [
    {
      "id": "positive_sum",
      "argv": ["python", "-c", "from calculator import add; print(add(2,3))"],
      "stdout": "5\n"
    },
    {
      "id": "negative_sum",
      "argv": ["python", "-c", "from calculator import add; print(add(-4,1))"],
      "stdout": "-3\n"
    }
  ]
}
```

このimageで必要な依存が不足する場合は、operatorが依存入りの信頼するimageを準備して
digestを固定する。AI生成のDockerfileやrepositoryのsetup commandを自動でhost実行しない。
各checkは1つの実挙動シナリオであり、stdoutに書かれたpytest/unittest件数は信用しない。
既存全回帰チェックが必要な変更では、それらを実行できるimageと十分な承認済みシナリオを
設定する。上記2件だけを任意の実プロジェクトの品質保証とは扱わない。

## 実行

```sh
uv run sf issue develop --config /absolute/path/to/operator-config.json \
  --confirm-run --confirm-bedrock
```

これは設定した範囲のsource/要件の送信、Bedrock推論、隔離command実行とDraft PR作成を
許可する操作。AWSリソース作成・デプロイ・mergeは含まない。
Docker/image事前確認に失敗した場合はAI推論を始めない。
実装とレビューは別のstateless Converse呼出し。実装・レビューの2推論ステップで、無限の課金ループはしない。
各Bedrock requestはconnect timeout 10秒/read timeout 60秒、SDK standard retry最大2回
（初回を含め各ステップ最大3試行、合計最大6試行）。
provider利用量はSDKのTokenUsageとして返る。料金の見積もりや予算上限サービスではない。

成功時だけ、以下の形式を返す。

```json
{"run_id":"...","status":"draft_pr_created","pull_request":{"external_id":"...","url":"..."}}
```

テスト失敗、推論不正、独立レビュー不足/must-fix、scope変更、base変更、保存失敗なら
PR配送へ進まない。host worktreeをAIが直接編集せず、元snapshotと同じbytesを検証/配送する。
プロンプト/ファイル/レビューは外部AIへ送られるため、公開してよいscopeを設定すること。

## 途中停止と復旧

同じdata rootのcontrollerは推論を含めて直列実行する。配送前にintentをfsyncし、
未解決の同一repoへ別Runを配送しない。モデル/テスト/レビュー失敗には新しいRunが必要。
出力のrun_idと `development-v1/<run_id>/state.json`、既存のRun/evidenceを確認する。
このartifactには要件、変更案、各checkのbounded実出力/終了結果、モデルのtoken利用量を保存する。
CLIは秘密情報を含み得るSDK例外を表示せず、停止した段階とrun_idを返す。

reviewed段階以降で配送だけ停止した場合、同じ設定・同じRunを指定する。

```sh
uv run sf issue develop --config /absolute/path/to/operator-config.json \
  --confirm-run --resume RUN_ID
```

resumeはAIを呼ばず、Bedrock課金確認フラグや認証を必要としない。同じoperator設定と
検証済みartifactへのローカル承認を更新し、source/証跡を再検証する。
branch/PR pendingは実サービスで正確に照合し、見つからなくても再作成しない。
commit準備の結果不明、異なるbranch/SHA/marker、closed/ready/merged PRは停止する。
journalを消す・別data rootに変える方法で再送を強制しない。

## 今回の限界

初期経路は1つのcandidate、承認済みの挙動シナリオ、独立した1レビューを対象とする。
同じPRの指摘修正と子Issueの直列実行は[有限ワークフロー](bounded-issue-workflow.md)から使う。
[Web operator操作](local-web-execution.md)も同じcontrollerへ接続済み。
品質失敗を無制限に修正するloop、分散Worker、S3永続化は未実装。
成功したDraft PRも人間が変更全体と必要な回帰チェックをレビューしてから扱う。

要件分割の `issue plan` / `issue advance` は[要件資料の自動検出](requirement-discovery.md)に対応します。
単独の `issue develop` は従来の明示contextを使うため、分割と自動検出はplan/advanceから始めてください。
