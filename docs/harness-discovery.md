# Harness Discovery v1

`sf_factory.harness_discovery.discover_harness` は、明示されたローカルGit rootの
Harness候補を決定的に列挙する読取専用ライブラリです。CLI/API接続、構文検証、承認、
Composition、適用は後続工程です。

```python
from dataclasses import asdict
from pathlib import Path
from sf_factory.harness_discovery import discover_harness

result = discover_harness(Path('/workspace/generic-software-factory'))
metadata = asdict(result)
```

候補は `AGENTS.md`、`harness/` 内のテキスト形式、`config/project*.yaml`/`.yml`、
`pyproject.toml`、`package.json`、`.github/workflows/*.yaml`/`.yml`。
入れ子の候補も検出します。scopeは候補が属するプロジェクトディレクトリであり、
適用順や実行権限を確定しません。複数ルール候補はValidationが必要な警告になります。

結果はschema version、相対path、分類、scope、SHA-256、検出根拠、問題一覧、completeです。
内容は返しません。名前による機密候補除外は内容の機密性を保証しません。
ハッシュも含め、結果の外部送信は本ライブラリでは行いません。

既定の上限は走査10,000エントリ、深さ32、候補1ファイル64 KiB、総読込1 MiB。
依存・生成物・Git metadataディレクトリは対象外です。
未対応Harness形式、symlink、機密名、読取失敗、binary/非UTF-8、上限到達、
観測した途中変更はissuesへ記録します。issuesがあればcompleteはfalseです。
complete=trueでも、未知のHarness規約や全言語を網羅したという意味ではありません。
不完全な結果を「Harnessなし」と判断して生成・適用へ進めないでください。

POSIXのdescriptor-relative open、O_NOFOLLOW、通常ファイル検査を使用します。
ファイルは読込前後のinode・サイズ・変更時刻を照合し、ディレクトリの変更も確認します。
非対応環境では拒否します。`.git` の通常ファイル/ディレクトリを確認しますが、
Gitオブジェクトの完全性やorigin、submodule境界、指示の妥当性は検証しません。
同時に攻撃者が変更できるホスト上の完全なsnapshotやOS隔離を保証するものではありません。
実行へ適用する際は信頼されたsnapshotと承認済みrevisionを使う必要があります。
