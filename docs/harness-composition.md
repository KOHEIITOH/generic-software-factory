# Harness Composition v1

`sf harness compose <repository> --target <scope> --select <path> ...
--exclude <path> <reason> ...` は、適用候補と順序を明示する読取専用操作です。

```sh
.venv/bin/sf harness compose . --target . \
  --select harness/principles/FACTORY_PRINCIPLES.md \
  --select harness/policies/SAFETY.md \
  --select harness/agents/planner.md \
  --select harness/agents/developer.md \
  --select harness/agents/tester.md \
  --select harness/agents/reviewer.md \
  --exclude config/project.example.yaml '例示用テンプレートで実行設定ではない'
```

対象scopeへ適用するすべてのルール候補について、選択するか理由付きで除外します。
ルール候補はAGENTS.md、harness/、ProjectProfile。manifest/CIは検証・fingerprintの根拠であり、
指示として選択しません。対象の親scopeの規約は候補になりますが、子/兄弟scopeは含めません。
候補にないpath、重複、選択と除外の重なり、未分類候補を拒否します。

選択順はcontextの提示順として保持します。これは権限の優先順位ではなく、自然言語ルールの
矛盾を解決した保証でもありません。Factoryの強制Policyは選択対象の外で、弱められません。
Profileのcommandを暗黙にmergeせず、採用するProfileは最大1つです。
例示Profileは除外が必要で、採用できません。不正構文・読込失敗・走査上限などは
理由付き除外でも回避できません。重複候補警告だけを、完全な明示選択によって解決します。

出力には対象scope、順序付きsource metadata、採用Profile、除外理由、inventory hash、
bundle hashを含みます。内容/commandは出力せず、承認・適用・外部送信は行いません。
選択順/対象/除外理由/候補/参照内容の変更はhashを変えるので、旧承認と一致しなくなります。
現時点では任意のTask overrideや外部Factoryルールのファイル読込は未対応です。

Compositionのbundle hashはHarnessApprovalRequest.bundle_hashへ渡せます。
適用時に同じ選択条件で再検証・再構成し、現在のrevision/hashと承認を照合する必要があります。
