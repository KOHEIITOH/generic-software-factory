# Offline Execution v1（実験的・R04a）

`docker_execution.run_offline_command` は信頼された制御側向けの、オフラインcommand実行器です。
CLI/Web/AI実行権限には接続していません。Task/Repositoryの承認なしで任意コードを
自動投入するための入口ではありません。

入力は取得済みのdigest固定image、argv tuple、1〜60秒のtimeout、最大1 MiBの出力上限。
imageは制御側がTLS検証を維持した公式registry等から事前取得してください。
本実装はpullをせず、tag指定を拒否します。承認済みimageのallowlist管理は後続です。

ローカルDocker socketに接続し、container作成後に設定をinspectしてから起動します。
非root、cap-drop ALL、no-new-privileges、read-only rootfs、network none、private IPC、
CPU 1 core、memory/swap各256 MiB、PID上限64、init、ログ保存無効を強制します。
workspaceとtmpは各16 MiBのtmpfsで、ホストmountは一切ありません。
Dockerが既定で挿入するproxy環境は空にし、ホストの任意環境変数をcontainerへ渡しません。

出力はpipeから上限まで読み、超過/timeoutでcontainerを強制削除し、CLIも終了させます。
終了コードと成功/失敗/timeout/出力超過/回収失敗を区別します。回収に失敗した場合は
container識別のため `sf.execution=offline-v1` labelで調査できます。他処理が作った
containerを一括削除しないでください。ホスト/daemon停止時の永続的な回収はR07で扱います。

## 実機試験

公式image `python@sha256:09a17cad02668ae61ece136b4fd36ac3849e14f670ebedb637ea3e15580525bc`
をTLS/checksum検証付きで取得し、Linux Docker 29.9.2で確認しました。

```sh
SF_TEST_DOCKER_IMAGE=python@sha256:09a17cad02668ae61ece136b4fd36ac3849e14f670ebedb637ea3e15580525bc \
  .venv/bin/pytest tests/test_docker_execution.py -q
```

同梱calculator相当のtmpfs内編集・実行、非root、ホストsocket/path/環境の非公開、
rootfs書込拒否、rootへの昇格拒否、ネットワーク拒否、子プロセスを含むtimeout回収、
出力上限、実際の終了コードを試験します。通常CIではimageが明示されない実機試験は
skippedです。モック試験の成功を実機試験の成功と読み替えません。

## 残る範囲

Repository snapshot/成果物転送、Task単位承認、RunのDB保存、cancel/restart回収、
command allowlist、image allowlist、AI接続用の限定ネットワーク/credential brokerは未実装です。
ImplementationPlanは引き続きready=falseです。Dockerはホストkernelを共有し、
kernel/daemon侵害への完全な隔離を保証しません。高リスクの第三者コードは別VM等も必要です。
