# Harness Validation v1

`sf harness validate <repository>` はDiscoveryの新しい結果に対して、YAML/JSON/TOMLの
構文とProjectProfile候補を読取専用で検査します。JSONをstdoutへ返し、0=検証問題なし、
1=問題あり、2=起動エラーです。0は承認・commandの安全性・実行許可ではありません。
ファイル内容とcommand本文を出力せず、モデルや外部サービスへ送信しません。

YAMLはSafeLoaderを使い、alias、重複キー、深さ32を超える構造を拒否します。
JSONの重複キー/非標準定数、不正なTOML、mappingでないmanifest/CI/Profileを拒否します。
CI固有schemaの意味や依存関係は検証しません。

初期ProjectProfile schemaは `generic-software-factory/v1alpha1`、`kind: ProjectProfile`。
metadata.name、spec.language、spec.repositoryRoot（`.`のみ）、spec.commands.test、
spec.definitionOfDone（空でない文字列の一覧）を必須とします。commandキーは
 test/lint/build/securityに限定し、未設定の`<configure-...>`を拒否します。
commandは提案として扱い、shell安全性を判定したり実行したりしません。
`.example.`のProfileは有効化せず問題一覧へ記録します。

architectureDocs/conventionsはscopeに対する相対テキストpathで、最大64参照。
親参照・絶対path・symlink・隠しpath・機密名は拒否し、UTF-8のmd/txt/rst/adocに限定します。
安全な読込後、参照pathと内容hashだけを結果へ保存します。検出した候補も再読込してhashを
照合します。各読込64 KiB、追加総読込1 MiBを上限とし、解析失敗した読込も予算へ加算します。

複数ルール候補の問題は残し、勝手に優先順位を決めません。Composition/Approvalが後続です。
ProfileCandidateは構造上確認できた候補であり、全体のvalid=false時も診断用に返します。
全体に問題があれば後工程で適用しないでください。
検出と検証は完全なfilesystem snapshotではなく、同時変更の完全排除やSecret内容検出を
保証しません。実行前には信頼されたrevisionと承認対象hashへの固定が必要です。
