import { useEffect, useState } from "react";
import { operatorApi } from "./operatorSession";

type Check = { id: string; argv: string[]; stdout: string };
type Proposal = { id: string; fingerprint: string; kind: string; name: string; status: string;
  repository: string; provider: string; issue: string; allowed_paths: string[]; checks: Check[]; image: string;
  selected_harness: string[]; excluded_harness: [string, string][];
  project_harness: { project: string; rules: { name: string; text: string }[] } | null;
  run_id?: string; profile: { id: string } | null };
type Inspection = { repository: string; root: string; revision: string; files: string[];
  test_preset: string | null; image: string; test_argv: string[] | null; test_stdout: string | null;
  harness: { path: string; kind: string }[]; validation: { path: string; code: string }[] };
async function api(path: string, options: RequestInit = {}) {
  const response = await operatorApi("/setup" + path, options);
  if (!response.ok) throw new Error(response.status === 409 ? "対象の版・設定が変わりました。内容を確認して作り直してください。" : "設定を確認できません（" + response.status + "）。Git root・origin・変更範囲・テストを確認してください。");
  return response.json();
}
export default function SetupPanel({ onApplied, refreshKey }: { onApplied: (id: string) => Promise<void>; refreshKey: string }) {
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
    if (busy) return;
    setBusy(true); setError("");
    try { await task(); } catch (e) { setError(e instanceof Error ? e.message : "設定エラー"); }
    finally { setBusy(false); }
  }
  function invalidate() { setProposal(null); setApproved(""); }
  async function inspect() {
    const data: Inspection = await api("/inspect", { method: "POST", body: JSON.stringify({ root, repository }) });
    setInspection(data); setRepository(data.repository); setRoot(data.root); setImage(data.image);
    setPaths(data.files.slice(0, 32).join("\n")); setName(data.repository);
    setCommand(data.test_argv ? JSON.stringify(data.test_argv) : "");
    setStdout(data.test_stdout || ""); invalidate();
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
    <form onSubmit={e => { e.preventDefault(); void perform(inspect); }}>
      <label>対象Repositoryの絶対パス<input aria-label="セットアップのRepositoryパス" value={root} disabled={busy} onChange={e => { setRoot(e.target.value); setInspection(null); invalidate(); }} placeholder="/Users/you/projects/my-service" /></label>
      <label>GitHub Repository（省略時はoriginから自動検出）<input aria-label="セットアップのGitHub Repository" value={repository} disabled={busy} onChange={e => { setRepository(e.target.value); setInspection(null); invalidate(); }} placeholder="owner/repo" /></label>
      <button type="submit" disabled={busy || !root}>リポジトリとHarnessを確認</button>
    </form>
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
