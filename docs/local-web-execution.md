# Webから開発を実行・再開・停止する

対象はPC上の単一利用者向けです。既存のCLIと同じWorkflow・Harness・品質チェック・
GitHub Adapter・永続予算を使います。AWSリソース作成、デプロイ、mergeは行いません。

## Webでの初回設定・Harness生成

`uv run sf web --rebuild` で起動し、ターミナルの操作リンクを開きます。
実行設定が未登録なら「初回設定・Harness生成と改善」が開きます。

1. GitHubのRepository一覧から対象を選び「このRepositoryを取得して初回設定へ」。一覧は初回設定画面を開いたときに読み込みます。手動clone・絶対パス入力は不要です。
2. AI、変更可能ファイル、検証内容と固定Dockerイメージを確認します。既存Harnessは検出・検証して再利用し、ない場合は最小の共通ルールを生成します。
3. 「設定とHarnessの案を作成」で表示された内容と除外Profileを確認し、承認して登録します。
4. 登録した設定でIssueを選択し「同意して実行・Draft PR作成」を押します。

設定JSONの手作業や `sf operator register` は不要です。設定はFactoryのprivate保存先に作成し、
取得元Repositoryへファイルを書き込みません。取得・案作成・登録ではAI推論・Docker実行・GitHubへの変更は行いません。
GitHub/AIの認証、Docker、固定イメージは利用PCで事前に準備します。秘密情報はWebへ入力しません。
取得したソースは、Factoryの起動Repositoryや保存データと分離したSF専用の場所で管理します。手動パス指定は「既存のローカルRepositoryを使う」に残します。その場合だけ、保存先と開発対象が重ならないよう指定します。
Python unittest/pytestを静的に検出できれば検証案を用意します。0件・skip・失敗・expected failureは不合格です。
pytest等の依存は実行イメージに含めてください。未検出の方式は詳細欄で検証argv・期待出力を指定します。
要件分割・CLI用の親Issue番号は詳細欄で指定できます（初期値1）。通常の実行は画面で選んだIssueを使います。
このwizardではアプリsourceの変更範囲を最大32ファイルに限定し、テスト・依存設定・Harnessは変更対象にしません。
既存のProject Profileは自動でコマンド権限へ変換せず、適用除外を明示して独立の検証設定を承認します。

### 既存CLIで登録する場合

[Issue開発の設定](local-issue-development.md)を対象repo外のoperator所有ファイルに用意し、
`data_root` とWebの `SF_DATA_DIR` を同じ絶対パスにします。

```sh
export SF_DATA_DIR=/absolute/path/to/factory-data
uv run sf operator register --config /absolute/path/operator.json --name 開発対象
uv run sf web --rebuild
```

どちらも登録は初回だけです。次回からは `uv run sf web --rebuild` で起動できます。
設定変更は新しい案の内容を確認して登録するか、CLIで再登録します。
失効するには `uv run sf operator revoke PROFILE_ID` を使います。失効済み設定は再送で復活させません。

起動時にブラウザが開き、ターミナルにも操作リンクを表示します。そのリンクは
操作権限を含むため共有しないでください。能力はURLのfragmentから一度だけ交換し、
すぐアドレスバーから除去します。HTTP queryやaccess log、localStorageへ保存しません。
通常のURLから開いた閲覧用画面だけでは実行できません。操作cookieはHttpOnly / SameSite
Strict、8時間で失効し、サーバー再起動または「操作権限を閉じる」でも無効になります。
`uvicorn sf_factory.web_api:app` など直接起動したAPIには実行権限を付与しません。

## 操作

通常は「開発を進める」で登録設定（Repository）と開いているIssueを選び、
表示した実行範囲とBedrockの料金説明を確認し、
**「同意して実行・Draft PR作成」**を押します。このボタンが今回の実行と料金発生への明示同意です。実装・承認済みテスト・独立レビュー・
Draft PR作成を1ジョブで実行します。Issueの手動取り込み・Repositoryの手動紐付け・
Project登録・Run ID入力は不要です。PRへのリンクと停止理由は画面に表示します。
品質条件を満たさない場合は停止し、mergeやreleaseは行いません。

登録設定の `issue` はCLIおよび詳細の要件分割用です。通常の実行では選択したIssue番号だけを
同一Repository内で差し替え、root・変更可能path・テスト・Harness・Runtime・image・
data_rootは変更しません。元設定のfingerprint・失効はworkerの各操作境界で再確認します。
明示した参照資料、または既存ルールで自動検出したREADME・仕様文書を読み取り、
参照資料を変更する提案は停止します。大きな要件は下記の分割・承認機能を使ってください。

同じIssue・設定・レビュアーで再実行すると保存済みのRun/PRを照合します。
成功済みPRを重複作成せず、予算をリセットしません。推論中の中断・品質失敗は
新しい候補を自動生成しません。レビュー済みの配送中断のみ既存Runを再照合できます。
新しいIssueは独立した有限予算を持ちます。設定変更を再実行ボタンの代わりに使わないでください。

診断・要件分割・レビュー対応は **「詳細設定・要件の分割・レビュー対応」** にまとめています。
信頼するレビュアーはカンマ区切りで指定でき、省略時はGitHub認証ユーザーです。
同じ登録設定のレビュアー範囲は初回ジョブで固定します。詳細の分割対象は登録設定の親Issueです。

- **計画案を作成・確認**：既存source/Harnessに基づく分割と独立レビューを行い、子Issue作成前に確認・承認を待ちます。
- **次の1ステップを実行・再開**：子Issueの実装・挙動検証・独立レビュー・Draft PR、または既存PRのレビュー修正・マージ確認を進めます。
- **同じPRの指摘に対応**：元のFactory製Draft PRを作成したRun IDを指定し、既存の単独PRを修正します。
- **停止を要求**：未開始ジョブは停止し、実行中は次の操作境界で停止します。処理中の推論・API・テストが終了して結果を記録する場合があります。

同じdata rootではWebの実行は1つだけです。1ステップで必ず戻り、レビュー待ちから
タイマーで勝手に次へ進めません。人間がPRを確認・mergeした後、明示的に次のステップを
実行します。子Issueの依存はPRの正確なheadのmergeで解除します。

画面には子Issue/PRリンク、Run ID、使用済み・残り予算、期限、判断・停止理由、
操作履歴を表示します。実行中の自動更新はローカル保存状態を読むだけです。
source/要件の全文、生のSDKレスポンス・例外、秘密情報、設定ファイルのパスは返しません。
新規の承認必須計画では、人の判断に必要な派生した要件解釈・分割案を認証済み画面に表示します。

## 復旧の扱い

送信結果が不明な場合、「同じ送信を確認」は同じrequest IDを使います。二重ジョブを作りません。
Webを再読み込みしても進捗・予算を維持します。サーバー再起動後は操作リンクを開き直します。
workerは独立プロセスなので生存していれば継続し、POSIX lease消失なら「中断」と表示します。
PID番号だけで生存と判断したり、再起動時に自動実行したりしません。

中断後の「再開」は既存Workflowの証跡を照合します。結果不明の推論・commit準備は
再送せず停止し、Issue/link/branch/PRの結果不明は既存のreadback規則を使います。
停止が安全上terminalになった場合、画面操作で解除・予算リセットはしません。
設定失効や変更も次の操作境界で反映します。ログアウトだけでは実行中workerを停止しません。

workerは最大1時間、Workflowは既存の累積回数・token/API/write・7日期限を維持します。
記録は `web-jobs-v1` / `automation-v1` / 既存Run・証跡に残します。
ジョブ履歴は最大500件で、上限時に勝手に古い証拠を削除しません。
DBは不要、現段階ではPOSIXローカル保存先を使います。複数利用者の公開サービス、
分散Worker、ECS/S3保存は今回の対象外です。

検証では実HTTP/保存とChromium、実Docker workerケースを使用し、AI/SCMは模擬します。
Bedrock＋GitHubの実サービス最終通し確認は、引き続き利用者のPCで行います。

## 任意のProject管理

Project/Repositoryのメタデータ管理は専用の折りたたみ画面を開いたときだけ読み込みます。
通常のIssue実行にProject登録は不要です。Project共通Harnessは既存の実行設定から適用します。
手動取り込み・紐付け・デモPR・旧クイック開始・Runtime紹介カード・重複履歴は削除しました。

## 要件資料の自動検出

`context_paths` を指定すれば優先し、省略/空ならREADME・要件/仕様文書の候補を探します。
不足・矛盾を検知した場合は子Issue作成前に停止し、出典・解釈・分割の根拠を保存します。
上限と根拠の確認方法は[要件資料の検出](requirement-discovery.md)を参照してください。

## 実行準備の診断

登録設定を選び「実行準備を確認」で、設定・Git root/origin/Harness・AI設定・Docker資源制限・
固定image・Git認証設定の不足と対処方法を表示します。AI推論やimage pullは行いません。
「GitHub接続・権限を確認」は、明示操作で対象Repositoryの読み取りとAdapterのpush権限を確認します。
AWS認証/モデル利用、Issue/親子関連/PRの書込権限は未確認として残し、診断成功を実通し成功とは扱いません。

## 子Issueを作る前の計画確認

新しいWebの計画は「計画案を作成・確認」で作成します。この段階では子Issue/PRを作らず、
要件の解釈・出典、各作業の目的・受入条件・依存関係・変更範囲・checkを表示します。
「次の1ステップ」を先に押した場合も、計画が未承認なら承認待ちで止まります。

表示した内容を確認し「この計画・参照資料・変更範囲を確認し、子Issue作成を承認する」を
チェックして「この計画を承認して子Issueを作成」を押します。承認だけの処理はAIを呼ばず、
Bedrock課金同意は不要です。Issueへの書込同意は必要です。その後に実装の次ステップを実行します。
資料・親Issue・設定・計画・対象版の変更で古い承認は使えません。中断後も承認と累積予算を保持します。
既存CLIで承認済みの旧計画は再適用せず、従来の経路を維持します。

この確認のため、新規の承認必須計画だけ、認証済み画面に限定して派生した解釈・計画を表示します。
元のsource/要件全文、SDK例外、秘密情報、詳細なreview concernは返しません。

## 失敗RunからのHarness改善案

Webの開発実行が品質条件で停止した場合、受信済みのモデル出力・検証・レビューの記録を根拠に、
定型の改善案を自動作成します。AIによる自由生成ではなく、追加の推論料金は発生しません。
認証/通信/Dockerの失敗を品質改善とは扱わず、応答や検証証拠がない場合は案を作りません。
「初回設定・Harness生成と改善」の保存済み案から、根拠Run・追加ルール・変更範囲・検証を確認し承認します。

承認後は新しい設定を選択し、同じIssueを実行すると、改善したHarnessで再度テスト・独立レビューを行います。
元設定・失敗Runの予算・証跡は保持します。テストを弱めたり権限を広げたりして成功扱いにしません。
改善効果は次回の実行で検証し、ルールの追加だけで品質向上を断定しません。
同じRunにつき1案、同じRepositoryで最大5改善案、保存先全体で100案までです。自動適用・無限再試行はしません。

## 操作権限が切れたとき

画面上部のAPI接続表示と、開発操作の権限は別です。「操作権限：再接続が必要」の場合は、
起動ターミナルの操作リンクを開き直すか、画面の「操作リンク」に貼り付けて再接続できます。
同じタブでリンクを開く場合も再認証します。別タブで再接続済みなら「権限を再確認」を使えます。
リンクはマスク表示し、送信後は入力を消します。アプリはブラウザの保存領域に記録しません。
期限切れ・ログアウトでは同じサーバーのリンクを使えます。サーバー再起動後は新しいリンクが必要です。
再接続だけではAI実行・PR作成・中断した送信の再実行は行いません。実行の同意も確認し直します。


## GitHubから取得したRepositoryの扱い

取得は既存SCM Adapterの読取APIを使い、default branchの特定commitのソースを上限付きで保存します。
履歴全体のcloneやGit checkoutは行わず、hooks・filter・submodule・setup/installコマンドを実行しません。
取得対象は既存のremote source制約と同じ、最大1,000通常ファイル・合計8MiB・1ファイル1MiBです。
シンボリックリンク、submodule、機密/制御パス、切り詰められた応答は拒否します。変更可能なRepoだけ登録候補にします。
SF管理のbaselineは1保存先あたり64版まで保持し、自動削除や上書きはしません。

実行時はGitHubの現在のdefault branchを再確認し、特定revisionのsnapshotで実装・テスト・Draft配送します。
許可済みのHarness/manifest/CI等が変わっていればAI推論前に止め、再取得と設定確認を案内します。
通常のコード更新では手動git pullは不要です。既存の管理baselineや過去Runは変更しません。
ローカルbaselineのGit commitと実装対象のremote commitは別々に記録し、remote revisionを実行証跡に固定します。
取得中断後は同じ版・hashのpublication intentを照合し、公開前なら安全に取得し直せます。
既存の作業場所が変更されていた場合は上書きしません。

## Node / TypeScript / Reactの初回設定

rootの`package.json`と`package-lock.json`（npm lock v2/v3）を静的に読み、
Vitest/Jestのtest、`tsc --noEmit`のtypecheck、ESLintのlintを提案します。
対象のコマンドと変更範囲を確認してください。非対応のtestスクリプトを検出した場合は、
型・lintだけへ黙って置き換えません。testが存在しない場合はその旨を表示し、型・lintの
完了を自動テスト成功とは扱いません。Nextのbuild/devサーバー起動は自動提案しません。

初回だけ「Node依存の取得とDockerイメージ準備に同意する」にチェックして
「Node実行環境を準備」を押します（最大10分）。Docker内で固定Node/Pythonベースと
package.json/lockだけを使い、`npm ci --ignore-scripts`で公開npm registryから依存を取得します。
ホストでnpmやRepositoryのコードは実行せず、.npmrc・GitHub/AWS認証・作業ツリー全体は
ビルドに渡しません。install scriptsは無効です。非公開registry、git/file依存、workspaces、
yarn/pnpmやpostinstallが必須のパッケージはこの自動準備には対応していません。

準備後は固定ローカルimage ID（`sha256:...`）と検証案が設定され、通常のHarness承認から
Repository→Issue→実行へ進めます。lock/manifestハッシュは実行設定へ固定し、変更時は再承認が必要です。
イメージはlocal daemonに保存し、registryへpushしません。削除された場合は再準備してください。

実際の検証は従来どおり非root・network none・認証なし・固定CPU/memory/pids/time制限で実行します。
ソースは保持し、ビルドキャッシュ/レポートはコンテナ内の一時コピーへ書きます。
Vitest/Jestは実行レポートの0件・skip・todo・失敗を拒否します。型・lintは別チェックです。
依存取得と検証を分離し、実行時のnpm installやネットワーク利用で補いません。
