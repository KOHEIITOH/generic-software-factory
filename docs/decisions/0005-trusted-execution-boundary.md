# ADR-0005: 信頼されたExecution境界と段階的な隔離実証

- 状態: 採用（本ADRのマージ後に実装）
- 対応計画: R03/M2。Runtime契約を拡張する前にExecutionを独立させる。

## 背景

Factory.run_taskとWorkflow Runnerはread-onlyの限定経路で、Execution Adapterを持たない。
ExecutionGrantのapprovedやplan_implementationのprocess_isolatedは呼出元の値であり、
隔離を証明しない。Git worktreeは作業の分離であってOSの強制境界ではない。
Harness Validationのvalidも、承認やcommandの実行許可ではない。

## 決定

初期Execution AdapterはLinuxのローカルDocker daemonを利用する。まず信頼された
同梱サンプルのオフラインcommand実行だけで隔離特性を検証し、外部AIのネットワーク接続、
任意Repository編集、push/PR操作は有効化しない。この段階でImplementationPlanの
`ready=False`を解除しない。

### 信頼境界

| 対象 | 扱い |
| --- | --- |
| Factory・認証/承認ストア・Execution実装・Docker daemon/ホスト | 信頼された制御側。Agentから到達させない |
| Issue・Repository・Harness・生成コード・Agent出力 | 信頼しない。commandの提案や自己申告を権限へ昇格しない |
| 検証済みimage digest・command argv・resource policy | 制御側で固定。ユーザー文字列をDockerのオプションへ展開しない |
| workspace snapshot | Task/Run/Repository/revisionに結合した専用コピー。親checkout/.git/ホストpathを渡さない |
| Artifact/ログ | 信頼しない出力。サイズ・型・pathを制限し、認証情報を除去して保存する |

### 初期実行器の契約

- 入力: 制御側で許可したdigest固定image、空でないcommand argv、timeout、専用workspace。
  shell文字列連結は使わない。対象・上限・imageを実行前に検証する。
- 初期workspaceはテストが作成した専用ディレクトリのみ。実運用snapshot作成・所有権の検証は
  別機能とし、任意のWeb入力pathを直接mountしない。
- Docker endpointはローカルsocketに固定し、環境/context/TLS selectorで別daemonへ
  迂回しない。Docker registry設定は保持し、credential fileをAgentへmountしない。
- containerは非root UID/GID、read-only rootfs、cap-drop ALL、no-new-privileges、
  network none、PID/CPU/memory制限、サイズ制限tmpfs、専用workspaceだけのrw mount。
  初期R04aではホストmountを一切せず、専用workspaceもtmpfsとする。snapshotの受渡しは後続。
  host network/PID/IPC、privileged、Docker socket、ホストroot、credential mountは禁止。
- 制御側の環境をcontainerに継承しない。Docker既定のproxy環境もオフライン実行では
  空に固定する。ネットワークが必要なRuntimeは後段の別policyで設計する。
- 実行前にcreateしたcontainerをinspectし、設定が要求に一致しなければstartしない。
- 終了結果: succeeded/failed/timed_out、実際の終了コード、制限付きstdout/stderr、
  実行器識別、image digest、開始/終了、停止・回収結果。commandの成功と品質合格は別。
- timeout/cancelはcontainer全体を強制停止し、子プロセスの残留と回収を確認する。
  回収失敗を成功にしない。プロセス異常・daemon停止・不明な状態は安全側で停止する。

### R04の実機受け入れ試験

1. 同梱の小さなサンプルが専用workspaceを変更でき、終了コードと出力を回収できる。
2. 親checkout/他Task/ホストcanary/Docker socketがcontainer内に存在しない。
3. rootfs書込・権限昇格・許可外ネットワーク接続が失敗する。
4. timeoutで子プロセスも停止し、専用containerが残らない。
5. 無効image/制限/不正mount/inspect不一致では開始前に拒否する。
6. Agentに渡していないhost環境canaryが出力に現れない。出力上限が強制される。

モック試験と実機試験を区別する。image取得の許可やDocker機能が不足する環境では実機試験を
未実施として明示し、スキップを隔離成立の証拠にしない。最初のimageは公式配布元からTLS検証を
維持して取得し、取得したRepoDigestをテスト記録へ固定する。

### 後続接続の条件

R05で承認を本人・Task・Repository・操作・入力hash・期限に結び付け、R06/R07でRunの永続化・
停止・再起動後回収へ接続する。R08で承認済みHarnessとsnapshotを渡す。AI Runtime接続時には
許可先限定の制御側credential broker、ネットワーク強制、漏えい負例試験を追加し、各Runtimeの
能力差を明示する。オフラインcommand実行の成功をAI実行の安全性証明に流用しない。

## 代替案と制約

worktreeだけの実行は隔離にならないため採用しない。Runtimeごとのsandbox自己申告だけにも
依存しない。初期から全OS/VM/clusterを実装せず、2つ目の具体的Execution実装で契約を検証する。
Dockerはホストkernelを共有し、ホスト/daemon侵害やkernel escapeを防ぐ完全な境界ではない。
高リスクの第三者コードには、別ホスト/VM等のより強い隔離を選択できるようにする。

既存PR #65のDocker availability判定は再利用候補だが、隔離証拠にはしない。
ローカルsocket固定のない現状では、この契約のready判定へ直接接続しない。
