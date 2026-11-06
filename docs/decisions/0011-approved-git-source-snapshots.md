# ADR-0011: 実行用ソースは承認commitのGit blobから組み立てる

- 状態: 採用（マージ後）。R04c。

親checkout/worktreeを実行器へmountすると、.gitやhost資格情報、未追跡ファイル、
準備後の変更まで混入し得る。prepared Runの承認commitからblobを列挙し、
検証済みHarnessの内容hashと照合して、非公開領域へ制限付きsnapshotを作る。

archiveの解凍をhostで行わず、通常blobと安全な相対pathだけを扱う。hooks/filtersを実行せず、
Git replaceとlazy fetch/network protocolも無効にする。host上でsourceを実行しない。
Git modeはmetadataで保持し、保存ファイルには実行権限を付けない。

Run/commit/bundle/全ファイルmetadataをhashへ結合し、使用前にdescriptor-relative読込で
再検証する。host storage自体は信頼境界内であり、暗号署名や改変不能媒体ではない。
資源制限された実行先へ転送する処理と、実装結果の受入れは別の明示的な工程とする。
