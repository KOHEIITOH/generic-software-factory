# ADR-0008: Harness承認の消費とprepared Runの保存を原子的に行う

- 状態: 採用（マージ後）。R06a。

承認の消費後にRun保存が失敗すると、承認だけ失われる。別々のDB操作を繋がず、
既存Factory DBで承認・Run・manifest・監査イベントを同じBEGIN IMMEDIATEへまとめる。
同じ承認を並行利用してもRunは1つだけ作成する。

Project RegistryとTask Project関連付けを再利用し、初期対象は登録済みlocal-git。
実Gitのroot/HEAD/clean状態と現在のComposition hashを、承認対象へ照合する。
検証後も実ファイルを固定するsnapshotではないため、実行前には別の再検証を必須とする。

Runtime未起動を明確にするためRun状態preparedと、runtime=unassigned/空workspaceを使う。
これは既存read-only run_taskとは別経路であり、prepared Runを実行するAPIを追加しない。
既存Runの表示を維持し、prepared Runにはversion付きのharness_manifestを追加する。
