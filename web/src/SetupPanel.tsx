import { useEffect, useRef, useState } from "react";
import { operatorApi } from "./operatorSession";

type Check = { id: string; argv: string[]; stdout: string };
type Proposal = { id: string; fingerprint: string; kind: string; name: string; status: string;
  repository: string; provider: string; issue: string; allowed_paths: string[]; checks: Check[]; image: string;
  selected_harness: string[]; excluded_harness: [string, string][];
  project_harness: { project: string; rules: { name: string; text: string }[] } | null;
  run_id?: string; profile: { id: string } | null };
type RepositoryChoice = { repository: string; can_push: boolean };
type Inspection = { managed?: boolean; remote_revision?: string; repository: string; root: string; revision: string; files: string[];
  test_preset: string | null; image: string; test_argv: string[] | null; test_stdout: string | null;
  harness: { path: string; kind: string }[]; validation: { path: string; code: string }[] };
const setupMessages: Record<string, string> = {
  scm_credentials_missing: "WebプロセスにGitHub認証が設定されていません。GH_TOKENまたはGITHUB_TOKENを設定して再起動してください。gh auth loginだけでは接続されません。",
  scm_credentials_rejected: "GitHubが認証を拒否しました（401）。トークンの期限・失効・設定を確認してください。",
  scm_access_denied: "GitHubがアクセスを拒否しました（403等）。対象Repositoryへのアクセス、Contentsの読み取り権限、組織のSSO承認を確認してください。",
  scm_repository_unavailable: "GitHubで対象Repositoryを確認できません（404）。Repositoryの存在とトークンのアクセス対象を確認してください。非公開Repositoryの権限不足でも発生します。",
  scm_rate_limited: "GitHubのAPI利用制限に達しました。連続再試行せず、制限が解除されてから取得してください。",
  scm_timeout: "GitHubとの通信がタイムアウトしました。PCのネットワーク・プロキシ接続を確認してください。",
  scm_source_deadline: "Repositoryのファイル取得が120秒の制限に達しました。認証エラーではありません。",
  scm_source_limit: "Repositoryが取得上限を超えています（1,000ファイル・合計8MiB）。",
  scm_source_type: "取得対象に非対応のオブジェクト、symlink・submodule、または1MiBを超えるファイルがあります。",
  scm_source_inventory: "GitHubから完全なファイル一覧を取得できませんでした。省略された一覧や2,000件を超える一覧は使えません。",
  scm_response_invalid: "GitHubの応答を安全に検証できませんでした。認証成功とは判定していません。",
  scm_unavailable: "GitHubへの通信に失敗しました。PCのネットワーク・プロキシとGitHubの稼働状況を確認してください。",
  state_overlap: "対象RepositoryとSFの状態保存先が重なっています。GitHubのRepository選択から自動取得してください。既存のローカルRepositoryを使う場合はSF_DATA_DIRを対象Repositoryの外へ設定してください。",
  repository_missing: "指定した場所または設定ファイルが見つかりません。Repositoryのパスを確認し、必要なら再取得してください。",
  worktree_dirty: "対象Repositoryに未コミットの変更・未追跡ファイルがあります。変更を保全してから再確認してください。自動削除・リセットは行いません。",
  repository_location: "Repositoryの場所を確認できません。Git直下の絶対パスを指定してください。~やsymlinkを含むパスは使えません。",
  repository_revision: "Gitのコミットを確認できません。コミット済みのRepository直下を指定してください。",
  git_filters: "対象RepositoryにGit filter設定があります。この実行方式では安全に取得できません。",
  repository_origin: "Git originと選択したGitHub Repositoryが一致しません。owner/repoとoriginの設定を確認してください。",
  change_scope: "変更可能なファイルは、重複のないアプリケーションソースを1〜32件指定してください。テスト・Harnessは変更対象にできません。",
  execution_image: "実行イメージは固定digest付きで指定してください（image@sha256:64桁の小文字16進数）。",
  behavioral_checks: "検証コマンド・期待出力が不正です。コマンドは文字列のJSON配列、期待出力は16KiB以内で指定してください。",
  harness_validation: "Harnessの検証で未解決の問題があります。「検出した注意点」を開いて確認してください。検証を省略して登録はできません。",
  source_types: "symlinkまたはsubmoduleを含むRepositoryは、この初回設定に対応していません。",
  source_size: "取得対象は1〜1,000ファイルのRepositoryに限られます。",
  setup_name: "設定名は1〜100文字で入力してください。",
};
const setupFields: Record<string, string> = { root: "Repositoryの場所", repository: "GitHub Repository", name: "設定名（1〜100文字）", provider: "AI", image: "実行イメージ", allowed_paths: "変更可能なファイル（1〜32件）", checks: "検証コマンド・期待出力", issue: "親Issue番号（正の整数）", fingerprint: "承認対象の版", confirmed: "設定の承認" };
async function api(path: string, options: RequestInit = {}) {
  const response = await operatorApi("/setup" + path, options);
  if (!response.ok) {
    const stage = path === "/acquire" ? "GitHub Repositoryの取得" : path.startsWith("/repositories") ? "GitHub Repositoryの一覧取得" : path === "/inspect" ? "Repository確認" : path.endsWith("/approve") ? "設定の登録" : path === "/proposals" && options.method === "POST" ? "設定案の作成" : "設定の読み込み";
    if (response.status === 409) throw new Error(stage + "：対象の版・設定が変わったか、保存上限に達しました。内容を再確認してください（409）。");
    const data = await response.json().catch(() => null);
    const code = data?.detail?.code;
    if (typeof code === "string" && setupMessages[code]) throw new Error(stage + "：" + setupMessages[code] + "（" + response.status + " / " + code + "）");
    // Only allowlisted field names are displayed. Never echo server input/exception text.
    const fields = Array.isArray(data?.detail) ? [...new Set<string>(data.detail.flatMap((e: { loc?: unknown[] }) => {
      const field = e.loc?.[1]; return typeof field === "string" && setupFields[field] ? [setupFields[field]] : [];
    }))] : [];
    throw new Error(stage + "に失敗しました（" + response.status + "）。" + (fields.length ? "入力を確認してください：" + fields.join("、") : "原因を特定できませんでした。押したボタンとこの表示を共有してください。"));
  }
  return response.json();
}
export default function SetupPanel({ onApplied, refreshKey }: { onApplied: (id: string) => Promise<void>; refreshKey: string }) {
  const operation = useRef(false);
  const [local, setLocal] = useState(false);
  const [catalog, setCatalog] = useState<RepositoryChoice[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [root, setRoot] = useState(""); const [repository, setRepository] = useState("");
  const [issue, setIssue] = useState("1");
  const [name, setName] = useState(""); const [provider, setProvider] = useState("bedrock");
  const [inspection, setInspection] = useState<Inspection | null>(null);
  const [paths, setPaths] = useState(""); const [image, setImage] = useState("");
  const [command, setCommand] = useState(""); const [stdout, setStdout] = useState("");
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [suggestions, setSuggestions] = useState<Proposal[]>([]);
  const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  const [approved, setApproved] = useState("");
  async function refresh() { setSuggestions((await api("/proposals")).proposals.filter((p: Proposal) => p.status !== "approved")); }
  useEffect(() => { void refresh().catch(e => setError(e.message)); }, [refreshKey]);
  async function perform(task: () => Promise<void>) {
    if (operation.current) return;
    operation.current = true; setBusy(true); setError("");
    try { await task(); } catch (e) { setError(e instanceof Error ? e.message : "設定エラー"); }
    finally { operation.current = false; setBusy(false); }
  }
  useEffect(() => { void perform(() => loadRepositories()); }, []);
  function invalidate() { setProposal(null); setApproved(""); }
  function inspectResult(data: Inspection) {
    setInspection(data); setRepository(data.repository); setRoot(data.root); setImage(data.image);
    setPaths(data.files.slice(0, 32).join("\n")); setName(data.repository);
    setCommand(data.test_argv ? JSON.stringify(data.test_argv) : "");
    setStdout(data.test_stdout || ""); invalidate();
  }
  async function loadRepositories(next: string | null = null) {
    const data = await api("/repositories" + (next ? "?cursor=" + encodeURIComponent(next) : ""));
    setCatalog(previous => Array.from(new Map<string, RepositoryChoice>((next ? [...previous, ...data.repositories] : data.repositories).map((item: RepositoryChoice) => [item.repository, item])).values()));
    setCursor(data.next_cursor);
    if (!next) { setRepository(""); setInspection(null); invalidate(); }
  }
  async function inspect() {
    inspectResult(await api("/inspect", { method: "POST", body: JSON.stringify({ root, repository }) }));
  }
  async function acquire() {
    inspectResult(await api("/acquire", { method: "POST", body: JSON.stringify({ repository }) }));
  }
  async function propose() {
    const argv: unknown = JSON.parse(command);
    if (!Array.isArray(argv) || !argv.length || !argv.every(v => typeof v === "string")) throw new Error("検証コマンドは文字列のJSON配列で指定してください。");
    setProposal(await api("/proposals", { method: "POST", body: JSON.stringify({ root, repository, name, provider, image, issue,
      allowed_paths: paths.split("\n").map(p => p.trim()).filter(Boolean), checks: [{ id: "behavior", argv, stdout }] }) }));
    setApproved("");
  }
  async function apply(value: Proposal) {
    if (approved !== value.fingerprint) return;
    const result: Proposal = await api("/proposals/" + value.id + "/approve", { method: "POST",
      body: JSON.stringify({ fingerprint: value.fingerprint, confirmed: true }) });
    if (!result.profile) throw new Error("登録結果を確認できません。同じ案から確認してください。");
    await onApplied(result.profile.id); setProposal(null); setApproved(""); await refresh();
  }
  function preview(value: Proposal) {
    return <div className="setup-preview"><h4>{value.kind === "improvement" ? "実行結果に基づくHarness改善案" : "実行設定・Harnessの確認"}</h4>
      <p>{value.repository} · AI: {value.provider}</p>
      {value.run_id && <p>根拠のRun: {value.run_id}（候補生成・検証の停止記録。原因を断定するものではありません）</p>}
      <p>要件分割・CLIの対象: Issue #{value.issue}（通常の実行は画面で選んだIssue）</p><p>変更範囲: {value.allowed_paths.join(", ")}</p><p>実行イメージ: <code>{value.image}</code></p>
      <details><summary>承認する検証コマンドと期待出力</summary><pre>{JSON.stringify(value.checks, null, 2)}</pre></details>
      <p>既存Harness: {value.selected_harness.join(", ") || "なし"}</p>
      {value.excluded_harness.length > 0 && <p>適用しないProfile: {value.excluded_harness.map(([path, why]) => path + " · " + why).join(", ")}</p>}
      {value.project_harness && <><p>{value.kind === "improvement" ? "改善後のProject共通ルール" : "リポジトリを直接変更せず、以下の最小Project Harnessを生成します。"}</p>
        <ul>{value.project_harness.rules.map(r => <li key={r.name}><strong>{r.name}</strong>: {r.text}</li>)}</ul></>}
      <p>改善効果は未検証です。次回実行も同じ品質ゲートで検証します。検証を弱めず、変更権限を拡大しません。登録だけではAI推論・Docker実行・GitHubへの書き込みは始まりません。</p>
      <label className="operator-consent"><input type="checkbox" checked={approved === value.fingerprint} disabled={busy}
        onChange={e => setApproved(e.target.checked ? value.fingerprint : "")} />この変更範囲・検証・Harnessを確認した</label>
      <button type="button" disabled={busy || approved !== value.fingerprint} onClick={() => void perform(() => apply(value))}>この設定とHarnessを登録</button>
    </div>;
  }
  return <div className="setup-panel"><h3>かんたん初回設定・Harness管理</h3>
    <p>リポジトリを確認し、変更範囲と検証を承認すると実行設定を登録できます。設定ファイルの手作業は不要です。AI認証とDockerはPCの設定を使います。</p>
    {error && <p role="alert">{error}</p>}
    <div className="operator-toolbar"><button type="button" disabled={busy} onClick={() => void perform(() => loadRepositories())}>GitHubのRepositoryを取得</button></div>
    {catalog.length > 0 && <><label>Repositoryを検索<input aria-label="セットアップのRepository検索" value={search} disabled={busy} onChange={e => setSearch(e.target.value)} /></label>
      <label>GitHub Repository<select aria-label="セットアップのGitHub Repository選択" value={repository} disabled={busy} onChange={e => { setRepository(e.target.value); setInspection(null); invalidate(); }}>
        <option value="">選択してください</option>{catalog.filter(c => c.repository === repository || c.repository.toLowerCase().includes(search.toLowerCase())).map(c => <option key={c.repository} value={c.repository} disabled={!c.can_push}>{c.repository}{c.can_push ? "" : "（読み取りのみ）"}</option>)}</select></label></>}
    {cursor && <button type="button" disabled={busy} onClick={() => void perform(() => loadRepositories(cursor))}>Repositoryをさらに取得</button>}
    <button type="button" disabled={busy || !repository} onClick={() => void perform(acquire)}>このRepositoryを取得して初回設定へ</button>
    <p>取得は読み取り専用です。SF専用の場所へ保存し、手動clone・絶対パス入力は不要です。AIやセットアップコマンドは実行しません。</p>
    <details onToggle={e => setLocal(e.currentTarget.open)}><summary>既存のローカルRepositoryを使う（任意）</summary>
      {local && <form onSubmit={e => { e.preventDefault(); void perform(inspect); }}>
        <label>対象Repositoryの絶対パス<input aria-label="セットアップのRepositoryパス" value={root} disabled={busy} onChange={e => { setRoot(e.target.value); setInspection(null); invalidate(); }} placeholder="/Users/you/projects/my-service" /></label>
        <label>GitHub Repository（省略時はoriginから自動検出）<input aria-label="セットアップのGitHub Repository" value={repository} disabled={busy} onChange={e => { setRepository(e.target.value); setInspection(null); invalidate(); }} placeholder="owner/repo" /></label>
        <button type="submit" disabled={busy || !root}>リポジトリとHarnessを確認</button>
      </form>}
    </details>
    {inspection?.managed && <p>GitHubから取得済み: {inspection.repository} · 版 {inspection.remote_revision}</p>}
    {inspection && <form onSubmit={e => { e.preventDefault(); void perform(propose); }}>
      <p>既存のHarness候補: {inspection.harness.map(h => h.path).join(", ") || "なし。最小Harnessを生成します。"}</p>
      {inspection.validation.length > 0 && <details><summary>検出した注意点</summary><ul>{inspection.validation.map((v, i) => <li key={i}>{v.path}: {v.code}</li>)}</ul></details>}
      <label>設定名<input aria-label="セットアップの設定名" value={name} disabled={busy} onChange={e => { setName(e.target.value); invalidate(); }} /></label>
      <label>AI<select aria-label="セットアップのAI" value={provider} disabled={busy} onChange={e => { setProvider(e.target.value); invalidate(); }}><option value="bedrock">Amazon Bedrock</option><option value="copilot">Copilot SDK</option></select></label>
      <label>変更可能なファイル（1行に1つ・最大32件）<textarea aria-label="セットアップの変更範囲" value={paths} disabled={busy} rows={5} onChange={e => { setPaths(e.target.value); invalidate(); }} /></label>
      {!inspection.test_preset && <p>安全に提案できるテスト方式を検出できませんでした。既存の検証コマンドと期待出力を指定してください。検証を省略して登録はできません。</p>}
      <details open={!inspection.test_preset}><summary>検証・実行イメージ・要件分割</summary><label>要件分割・CLI用の親Issue番号<input aria-label="セットアップの親Issue" value={issue} disabled={busy} onChange={e => { setIssue(e.target.value); invalidate(); }} /></label>
        <p>Python unittest/pytestの推奨設定は0件・skip・失敗を不合格にします。pytestと必要な依存は実行イメージに含めてください。依存関係はオフライン実行イメージに含めてください。ここではコマンドを実行しません。</p>
        <label>検証コマンド（JSON配列）<textarea aria-label="セットアップの検証コマンド" value={command} disabled={busy} rows={4} onChange={e => { setCommand(e.target.value); invalidate(); }} /></label>
        <label>成功時の期待出力（改行も一致）<textarea aria-label="セットアップの期待出力" value={stdout} disabled={busy} rows={2} onChange={e => { setStdout(e.target.value); invalidate(); }} /></label>
        <label>実行イメージ（固定digest・Python runnerを含む）<input aria-label="セットアップの実行イメージ" value={image} disabled={busy} onChange={e => { setImage(e.target.value); invalidate(); }} /></label>
      </details>
      <button type="submit" disabled={busy || !paths.trim() || !command}>設定とHarnessの案を作成</button>
    </form>}
    {proposal && preview(proposal)}
    <details><summary>保存済みの設定・改善案（{suggestions.length}件）</summary>
      <p>未承認の設定案と、失敗したWeb実行から自動作成する定型ルールの改善案を保存します。追加のAI料金は発生しません。自動適用はせず、元の設定・検証・証跡を保持します。同一Runは1案、Repositoryあたり最大5案です。</p>
      <button type="button" disabled={busy} onClick={() => void perform(refresh)}>改善案を更新</button>
      {suggestions.map(value => <div key={value.id}>{preview(value)}</div>)}
    </details>
  </div>;
}
