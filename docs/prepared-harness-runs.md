# 承認済みHarnessのRun固定（R06a）

`HarnessRunService` は既存Factory/Project Registry/Issue Project関連付け/Harness Approvalを
接続する、信頼されたローカル制御側向けのサービスです。Web/CLIからの承認入力は追加しません。

1. Issueが要求したProjectへ関連付けられ、登録済みlocal-git Repositoryのpathが一致することを確認。
2. Git root、exact HEAD、tracked/untrackedともcleanな作業ツリーを確認。
3. 現在のHarnessを再検証・明示構成し、承認したrevision/bundle hashとの一致を確認。
4. 同じFactory DBのtransaction内で、対象一致・期限・失効・未使用を確認して承認を消費。
5. Run、manifest metadata、監査イベントを同時に保存。失敗したら消費も含めてrollback。

Runは `status=prepared`、`runtime=unassigned`、`workspace=""` です。
旧schemaのstarted_atには準備記録時刻を格納し、Runtimeが開始したという意味にはしません。
Runtime起動、workspace作成、shell実行、ネットワーク、push/PRは行いません。
Git操作はローカルの設定名/root/HEAD/status確認だけで、fsmonitor/hooksを無効化します。
外部clean/processを起動し得るGit filter設定があるRepositoryは、statusより前に拒否します。
制御側が管理し同時書込がないcheckoutでの準備を前提とし、悪意ある同時変更への隔離保証はありません。

`Factory.show_run` と既存 `sf run show <id>` はprepared Runに限り `harness_manifest` を返します。
通常Runの従来の出力は維持します。manifestにはProject/Repository/Issue/revision/bundle hash、
対象scope、順序付きsource metadata、参照hash、除外理由を保存し、ファイル内容は含みません。
後からRepositoryが変わっても保存した記録は変わりません。

## 制約

- 登録済みlocal-gitのみ。GitHub origin/bindingによる識別は既存機能と別途接続する。
- callerが本人性とProject操作権限を検証する。ID文字列だけでは認証されない。
- 記録はmanifestであってimmutableなsource snapshotではない。準備後の変更を実行へ
  流用してはいけない。実行段階では実際のsnapshotと版を再確認する必要がある。
- Runをpreparedから実行状態へ進める機能は未実装。OS隔離不足を解除しない。
- 承認を消費した後の実行失敗では再承認が必要。同じreceiptを再利用しない。
- 同一DB transactionの原子性に依存する。分散DBや永続的なRun再開は後続。

独立Taskの移行互換は廃止。[外部Issueモデル](external-issue-model.md)を参照。
