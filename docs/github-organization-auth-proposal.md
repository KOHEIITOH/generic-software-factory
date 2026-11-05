# GitHub 認証・Organization・リポジトリ連携 設計案

> Status: Proposal / 未実装。現行のWeb UIにはGitHubログインやPrivate Repository一覧機能はない。

## 目標
- 利用者がGitHubでログインし、自分のアクセス可能な個人・Organization配下のPublic/Privateリポジトリを探せる。
- Factoryによる実際のアクセスは別途明示的に許可する。**閲覧できることとFactoryが操作できることは異なる**。
- Taskに対象リポジトリ（必要なら複数）を紐付け、将来のIssue取得・ブランチ作成・PR作成に利用する。
- GitHub専用の認証実装をFactory Coreに埋め込まず、Provider Adapterとして交換可能にする。

## 認証とアクセス許可を分離
1. **本人確認**: GitHub OAuthまたはGitHub App user authorizationで利用者を認証。OAuth callbackのstate/PKCE、セッション固定化対策、CSRF、SameSite/HttpOnly/Secure Cookie、ログアウトを実装。
2. **リポジトリ発見**: ユーザー権限で閲覧可能なリポジトリをページング取得し、owner・visibility・権限を表示。OrganizationのSSOや承認ポリシーによって表示できない場合は理由を案内。
3. **Factoryへのアクセス許可**: GitHub AppをOrganization/個人にインストールし、対象リポジトリと最小権限を選択。利用者の閲覧権限とAppのinstallation権限を交差検証する。
4. **実行権限**: Factory内のRole/Approval Gate/Risk Policyで別途判定。GitHub API権限があっても自動マージ・本番リリースを許可しない。

## 推奨フロー
GitHubでログイン → アカウント/Organization一覧 → リポジトリ検索（Public/Private） → 接続状況（未接続/承認待ち/接続済み） → 必要なリポジトリだけGitHub Appを許可 → Task作成時に対象を選択 → 権限・品質ゲートを通して実行。

GitHub Appのインストール範囲は「All repositories」または「Only select repositories」。Organization管理者の承認やSSOが必要な場合がある。GitHub AppをインストールしていないPrivate RepositoryをFactoryが操作することはできない。

## セキュリティ上の必須事項
- 認証トークン/installation token/秘密鍵はサーバー側のみで管理。フロント・ログ・DBの平文に残さない。暗号化・短期有効期限・ローテーション・失効に対応。
- ローカル開発ではループバックbindを強制。OAuth redirect URIの厳格な許可リスト、state検証、PKCE、セッション保護、CSRF対策を必須とする。既存のOrigin検査だけでは不十分。
- Organizationの許可とGitHub APIの権限を操作直前に再確認。接続解除・権限変更・インストール削除のWebhookを処理。
- Private Repositoryのコード・Issue本文・認証情報をAI Runtimeに無断送信しない。モデル/Provider別にデータ送信可否を明示し、企業ポリシーに従う。
- リポジトリ名・visibility・権限などのメタデータも利用者ごとにアクセス制御。ログに秘密情報を出さない。
- Webhook署名検証、権限の最小化、監査ログ、レート制限、ページング、エラー時の安全側拒否。
- ローカルシングルユーザーMVPとマルチユーザー・ホスティングを混同しない。

## 段階的実装（各段階を独立PRにする）
1. **Provider契約とモック**: identity、repository discovery、installation permissionを抽象化。Fake providerとテスト。外部認証はまだ有効化しない。
2. **GitHubログイン**: callback/state/PKCE/session/logoutの実装。ローカル設定・秘密情報管理と失敗テスト。
3. **リポジトリ発見UI**: 個人/Organization、Public/Private、ページング、検索、権限・接続状況表示。
4. **GitHub App接続**: installation selection、権限検証、承認待ち/失効/削除の扱い。
5. **Taskへのrepo紐付け**: 既存SQLiteマイグレーション、対象選択、アクセス再検証。
6. **安全な実行連携**: Execution Guardを信頼できる実行境界へ統合し、Issue→ブランチ→PRまで。マージは人間承認。

## 受入基準
- Private Repositoryが権限を持つ利用者だけに見え、Factory未許可なら操作できない。
- Organization配下の多数のリポジトリでページング・検索できる。
- 失効・SSO未承認・App未インストール・権限不足を区別できる。
- 他ユーザーのセッションやリポジトリへアクセスできない。
- 未接続・未認証の状態ではGitHub操作を拒否する。
- 企業のPrivateコードをAIへ送る前にProvider/データポリシーを評価する。

## ゴールと設計上の非目標
この構想のゴールは**特定企業のGitHub運用を再現することではなく、開発対象・SCM・AI・ホスティングに依存しない汎用Software Factory**である。Organization配下のPrivate Repositoryは重要な受入ユースケースの一つであり、唯一の対象ではない。

- 個人の単一Public Repository、個人Private Repository、Organizationの複数Private Repository、ローカルGit、将来のGitLab等を想定する。
- GitHubログインを唯一のログイン手段にしない。ローカル単独利用はGitHubアカウントなしでも成立させる。
- Factory CoreはGitHubのOAuth、installation ID、REST API、組織モデルに直接依存しない。認証・SCM・Repository DiscoveryはAdapterの契約として扱う。
- リポジトリ発見とコード操作を分離し、利用者が見えるリポジトリすべてへの書き込みを前提にしない。
- 企業固有のSSO・承認ルール・ポリシーはConfigurationまたはAdapterで吸収する。
- 初期実装でGitHubを優先しても、別のSCMを追加する際にCore変更が必須となる設計を避ける。

受入シナリオは最低限、(A) GitHub未接続のローカル利用、(B) 個人のPublic/Private、(C) OrganizationのPrivate、(D) GitHub以外のSCMをFake Adapterで差し替え、を含める。

## 信頼境界と失効時の挙動（レビュー追記）
- **Identity**（誰か）、**Discovery**（何が見えるか）、**Authorization**（Factoryが何を操作できるか）、**Execution**（AIが何を実行できるか）を独立した判定として扱う。ログイン済みだけではGitHub操作を許可しない。
- GitHub App installation tokenは対象installation・repository・権限に限定し、発行時とGitHub操作直前に権限を検証する。権限キャッシュを唯一の認可根拠にしない。
- ユーザーのアクセス権消失、App削除、OrganizationのSSO失効、対象リポジトリの移動・削除時は**安全側に停止**する。進行中タスクも次の外部操作前に再検証する。
- 複数利用者が同じFactoryを使う場合、Task・接続情報・監査ログの所有者を分離する。リポジトリ一覧のAPIレスポンスやキャッシュも利用者ごとにスコープする。
- OAuthによる本人確認とGitHub App installationの認可は別フロー。**GitHubログインなしのローカルモード**は継続できるが、そのモードでPrivate Repositoryへアクセスするには別途明示的な認証設定が必要。
- GitHub OAuthとGitHub Appのuser authorizationは採用候補であり、OAuth/PKCE対応状況・利用者権限での一覧取得方式・Organization SSOの制約は実装前に公式仕様で再検証する。
- 認証方式やリポジトリ接続が未設定の場合も、既存のローカルTask作成・閲覧機能は維持する。移行で既存ユーザーのデータを破壊しない。

## 実装レビューのゲート
1. Adapterの契約はGitHub固有型をCoreへ露出させない。
2. リポジトリ一覧にPrivate情報が混じっても、未認証者・別ユーザーに漏れない。
3. GitHub App未インストール・権限不足・失効・SSO制限を成功として扱わない。
4. 外部AIへコードを渡す前にデータポリシーの判定を行う。
5. ローカル単独利用の回帰テストと、Fake Providerによる他SCMの差し替えテストを通す。
