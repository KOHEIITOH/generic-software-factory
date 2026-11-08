import { useEffect, useRef, useState } from "react";

type RequirementSources = { mode: string; revision: string; fingerprint: string; review_status?: string;
  documents: { path: string; sha256: string; bytes: number; reason: string }[];
  assessments: { source_id: string; status: string }[];
  requirements: { id: string; sources: string[]; children: string[] }[] };
type Profile = { id: string; name: string; fingerprint: string; available: boolean; repository?: string; issue?: string; provider?: string; allowed_paths?: string[]; checks?: string[]; context_paths?: string[]; requirement_mode?: string };
type Progress = { requirement_sources?: RequirementSources | null; status: string; counts: Record<string, number>; limits: Record<string, number>; expires_at: string;
  children: { id: string; issue_id: string; issue_url?: string; status: string; run_id?: string; pr_url?: string }[];
  decisions: { at: string; code: string }[] };
type Job = { id: string; profile_id: string; config_fingerprint: string; action: string; reviewers: string[]; status: string;
  created_at: string; stop_requested: boolean; result: { status: string; reason?: string } | null; progress: Progress | null; events: { code: string }[] };
type Submission = { profile_id: string; config_fingerprint: string; request_id: string; action: string; confirm_run: boolean;
  confirm_bedrock: boolean; run_id: string | null; reviewers: string[] };
const active = (job: Job) => ["queued", "running", "stopping"].includes(job.status);
const labels: Record<string, string> = { queued: "実行待ち", running: "実行中", stopping: "停止処理中", stopped: "停止", interrupted: "中断・復旧確認が必要", finished: "ステップ終了", waiting: "次の操作・レビュー待ち", completed: "完了", ready: "次へ進めます", pending: "依存PRのマージ待ち", pr_open: "PRレビュー・マージ待ち", merged: "マージ確認済み", failed: "失敗", plan_ready: "計画と子Issueを作成しました", child_pr_submitted: "Draft PRを作成しました", awaiting_review: "レビュー待ち", awaiting_merge: "マージ待ち", repair_submitted: "同じPRへ修正を追記しました", child_awaiting_review_or_merge: "子PRのレビュー・マージ待ち", child_merge_verified: "子PRのマージを確認しました", all_child_prs_merged: "すべての子PRのマージを確認しました", remote_read_unavailable: "接続の再確認待ち", operator_or_execution_stopped: "停止または実行条件の確認が必要です", operator_step_approved: "実行を承認", worker_claimed: "workerが開始", operator_stop_requested: "停止を要求", worker_step_finished: "ステップ終了", worker_lease_lost: "workerの中断を検出", budget_exhausted: "試行・推論予算の上限に達しました", api_budget_exhausted: "API予算の上限に達しました", deadline_exhausted: "実行期限に達しました", candidate_repeated: "同じ変更案が繰り返されたため停止しました", base_changed_requires_new_candidate: "基準ブランチが変更されました", child_quality_failed: "子Issueの検証または独立レビューに失敗しました", parent_requirement_changed: "親Issueの要件が変更されました", child_requirement_changed: "子Issueの要件が変更されました", child_create_unresolved: "子Issue作成結果の照合待ち", child_link_unresolved: "親子関連の照合待ち", child_execution_outcome_unknown: "前の実行結果が不明なため停止しました", requirement_advance_stopped: "実行条件または権限を確認してください", advance_stopped: "実行条件または権限を確認してください", requirements_insufficient: "要件が不足しているため停止しました", requirements_conflicting: "要件に矛盾があるため停止しました", requirements_discovery_limit: "要件資料の読取上限を超えました。参照資料を明示してください", requirements_context_limit: "要件とコードの文脈が上限を超えました", requirements_source_missing: "指定した要件資料が見つかりません", requirements_source_invalid: "要件資料の形式・内容を確認してください", requirements_source_changed: "計画時から要件資料が変更されました", requirements_plan_rejected: "要件分割の独立レビューを通過しませんでした", requirements_reference_write_conflict: "参照した要件資料への変更を含むため停止しました", requirements_interpreted: "要件の解釈を記録しました", repository_readme: "README", root_requirement_document: "ルートの要件文書", requirement_document_convention: "要件・仕様・設計の文書候補", operator_context_path: "明示指定", explicit: "明示指定", auto: "自動検出", issue_only: "親Issueのみ", insufficient: "要件不足", conflicting: "要件の矛盾", requirements: "要件", supporting: "参考資料", irrelevant: "要件として不採用" };
const text = (code: string) => labels[code] || code;
async function api(path: string, options: RequestInit = {}) {
  return fetch("/api/operator" + path, { ...options, credentials: "same-origin", headers: {
    "Content-Type": "application/json", "x-sf-operator": "1", ...options.headers } });
}
// React StrictMode may repeat effects. Exchange the URL capability only once.
let bootstrap: Promise<void> | null = null;
function exchange() {
  if (!bootstrap) {
    const token = new URLSearchParams(window.location.hash.slice(1)).get("operator");
    if (token) window.history.replaceState(null, "", window.location.pathname + window.location.search);
    bootstrap = token ? api("/session", { method: "POST", headers: { Authorization: "Bearer " + token } })
      .then(r => { if (!r.ok) throw new Error("ターミナルの操作リンクを開き直してください。"); }) : Promise.resolve();
  }
  return bootstrap;
}
function Link({ url, label }: { url?: string; label: string }) {
  return url?.startsWith("https://") ? <a className="source-link" href={url} target="_blank" rel="noopener noreferrer">{label} ↗</a> : null;
}

export default function OperatorPanel() {
  const [auth, setAuth] = useState("loading");
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [selected, setSelected] = useState("");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [reviewers, setReviewers] = useState("");
  const [runId, setRunId] = useState("");
  const [consent, setConsent] = useState(false);
  const [bedrock, setBedrock] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [uncertain, setUncertain] = useState(false);
  const pending = useRef<Submission | null>(null);
  const inFlight = useRef(false);
  const profile = profiles.find(p => p.id === selected);
  const history = jobs.filter(j => j.profile_id === selected && j.config_fingerprint === profile?.fingerprint);
  const progress = history.find(j => j.progress)?.progress;
  const frozen = history[0]?.reviewers;
  const working = jobs.some(active);
  const enabled = profile?.available && !working && !busy && !uncertain && consent && (profile.provider !== "bedrock" || bedrock);

  async function refresh() {
    const [p, j] = await Promise.all([api("/profiles"), api("/jobs")]);
    if ([p.status, j.status].some(s => s === 401 || s === 403)) { setAuth("locked"); return; }
    if (!p.ok || !j.ok) throw new Error("状態を取得できません。保存済みの状態を保持しています。");
    const list: Profile[] = (await p.json()).profiles;
    setProfiles(list); setJobs((await j.json()).jobs);
    setSelected(value => value || list.find(item => item.available)?.id || ""); setAuth("ready");
  }
  useEffect(() => {
    let alive = true;
    void fetch("/api/operator/status").then(async r => {
      if (!r.ok || !(await r.json()).enabled) { if (alive) setAuth("disabled"); return; }
      await exchange(); if (alive) await refresh();
    }).catch(cause => { if (alive) { setAuth("locked"); setError(cause.message); } });
    return () => { alive = false; };
  }, []);
  useEffect(() => {
    if (!working || auth !== "ready") return;
    // Only read local status. Never start workflow steps from a timer.
    const timer = window.setInterval(() => { void refresh().catch(e => setError(e.message)); }, 4000);
    return () => window.clearInterval(timer);
  }, [working, auth]);

  async function send(payload: Submission) {
    if (inFlight.current) return;
    inFlight.current = true; setBusy(true); setError(""); setMessage("");
    pending.current = payload; setUncertain(true);
    try {
      const r = await api("/jobs", { method: "POST", body: JSON.stringify(payload) });
      if (!r.ok) {
        if (r.status < 500) { pending.current = null; setUncertain(false); }
        throw new Error("実行を受け付けられませんでした（" + r.status + "）。設定・同意・実行中の操作を確認してください。");
      }
      pending.current = null; setUncertain(false); setConsent(false); setBedrock(false);
      setMessage("1ステップを受け付けました。レビュー待ちになったら、人間の確認後に次へ進めてください。");
      await refresh();
    } catch (e) { setError(e instanceof Error ? e.message : "送信状態を確認してください。"); }
    finally { inFlight.current = false; setBusy(false); }
  }
  function submit(action: string) {
    if (!enabled || !profile) return;
    void send({ profile_id: profile.id, config_fingerprint: profile.fingerprint,
      request_id: crypto.randomUUID().replaceAll("-", ""), action, confirm_run: consent,
      confirm_bedrock: bedrock, run_id: action === "review" ? runId : null,
      reviewers: frozen || reviewers.split(",").map(s => s.trim()).filter(Boolean) });
  }
  async function stop(job: Job) {
    setBusy(true); setError("");
    try {
      const r = await api("/jobs/" + job.id + "/stop", { method: "POST" });
      if (!r.ok) throw new Error("停止要求を保存できませんでした。状態を再確認してください。");
      setMessage("停止を要求しました。処理中の推論・テストは終了する場合があります。次の操作前に停止します。");
      await refresh();
    } catch (e) { setError(e instanceof Error ? e.message : "停止エラー"); }
    finally { setBusy(false); }
  }
  return <section className="panel operator-panel" id="operator">
    <div className="panel-head"><span className="eyebrow">ISSUE → DRAFT PR</span><h2>開発を進める</h2>
      <p>登録した設定で1ステップずつ実行します。レビュー・マージ待ちで終了し、マージやリリースは人間が行います。</p></div>
    {auth === "loading" && <p>操作権限を確認しています…</p>}
    {auth === "disabled" && <p>PCのターミナルで <code>uv run sf web --rebuild</code> を使って起動してください。</p>}
    {auth === "locked" && <p>操作権限がありません。起動したターミナルに表示されたダッシュボードのリンクを開いてください。</p>}
    {error && <p role="alert">{error}</p>}{message && <p role="status">{message}</p>}
    {auth === "ready" && <>
      <div className="operator-toolbar"><button type="button" disabled={busy} onClick={() => void refresh().catch(e => setError(e.message))}>状態を更新</button>
        <button type="button" disabled={busy} onClick={() => void api("/logout", { method: "POST" }).then(r => { if (r.ok) setAuth("locked"); })}>操作権限を閉じる</button></div>
      {!profiles.length ? <p>実行設定が未登録です。同じ保存先を使うPCのターミナルで登録してください。<br />
        <code>uv run sf operator register --config /絶対パス/operator.json --name 開発対象</code></p> : <>
        <label className="project-selector">実行設定<select value={selected} disabled={busy || uncertain} onChange={e => {
          setSelected(e.target.value); setConsent(false); setBedrock(false); setRunId(""); }}>
          <option value="">選択してください</option>{profiles.map(p => <option key={p.id} value={p.id}>{p.name}{!p.available ? "（無効・再登録が必要）" : ""}</option>)}</select></label>
        {profile && <div className="operator-scope"><strong>{profile.repository} · 親Issue #{profile.issue}</strong>
          <p>AI: {profile.provider} / 変更範囲: {profile.allowed_paths?.join(", ")} / 検証: {profile.checks?.join(", ")}</p>
          <p>要件資料: {profile.context_paths?.length ? "明示指定（" + profile.context_paths.join(", ") + "）" : "自動検出（README・要件/仕様/設計の文書候補、最大12ファイル）"}</p>
          {!profile.available && <p role="alert">設定が変更・失効しています。ターミナルで確認し、登録し直してください。</p>}
          <label>信頼するレビュアー（カンマ区切り、省略時はGitHub認証ユーザー）<input aria-label="信頼するレビュアー"
            value={frozen ? frozen.join(", ") : reviewers} disabled={!!frozen || busy || uncertain} onChange={e => setReviewers(e.target.value)} /></label>
          <label className="operator-consent"><input type="checkbox" checked={consent} disabled={busy || uncertain} onChange={e => setConsent(e.target.checked)} />表示した範囲のAI送信・隔離テスト・Issue/PR操作に同意する</label>
          {profile.provider === "bedrock" && <label className="operator-consent"><input type="checkbox" checked={bedrock} disabled={busy || uncertain} onChange={e => setBedrock(e.target.checked)} />Bedrockの推論料金の発生に同意する</label>}
          <div className="operator-toolbar"><button type="button" disabled={!enabled} onClick={() => submit("plan")}>計画・子Issueを作成</button>
            <button type="button" disabled={!enabled} onClick={() => submit("advance")}>次の1ステップを実行・再開</button></div>
          <details><summary>既存の単独PRをレビュー修正</summary><label>最初にDraft PRを作成したRun ID<input aria-label="元のRun ID" value={runId} disabled={busy || uncertain} onChange={e => setRunId(e.target.value)} /></label>
            <button type="button" disabled={!enabled || !/^[a-f0-9]{32}$/.test(runId)} onClick={() => submit("review")}>同じPRの指摘に対応</button></details>
        </div>}</>}
      {uncertain && <p>送信結果が不明です。新しい操作を作らず、同じ依頼の受付状態を確認します。 <button type="button" disabled={busy} onClick={() => { if (pending.current) void send(pending.current); }}>同じ送信を確認</button></p>}
      {progress && <div className="operator-progress"><h3>Workflowの進捗：{text(progress.status)}</h3><p>期限: {new Date(progress.expires_at).toLocaleString("ja-JP")}</p>
        <div className="operator-budgets">{[["model", "max_model_calls", "推論回数"], ["tokens", "max_tokens", "予約token"], ["api", "max_api_calls", "API回数"], ["write", "max_writes", "書込操作"]].map(([key, limit, label]) => <span key={key}>{label}: {progress.counts[key].toLocaleString()} / {progress.limits[limit].toLocaleString()}（残り {Math.max(0, progress.limits[limit] - progress.counts[key]).toLocaleString()}）</span>)}</div>
        {progress.requirement_sources && <details className="requirement-sources"><summary>参照した要件資料・分割の根拠</summary>
          <p>{text(progress.requirement_sources.mode)} / 確認結果: {progress.requirement_sources.review_status === "ready" ? "要件を確認済み" : progress.requirement_sources.review_status ? text(progress.requirement_sources.review_status) : "未判定"}</p>
          <p>資料の版: <code>{progress.requirement_sources.revision}</code></p>
          {!progress.requirement_sources.documents.length && <p>文書候補はありません。親Issueの要件を判定します。</p>}
          <ul>{progress.requirement_sources.documents.map(d => <li key={d.path}><strong>{d.path}</strong> — {text(d.reason)}<small>SHA256: {d.sha256} · {d.bytes.toLocaleString()} bytes</small></li>)}</ul>
          <ul>{progress.requirement_sources.assessments.map(a => <li key={a.source_id}>{a.source_id === "issue" ? "親Issue" : a.source_id}: {text(a.status)}</li>)}</ul>
          <ul>{progress.requirement_sources.requirements.map(r => <li key={r.id}>{r.id}: {r.sources.join(", ")} → {r.children.join(", ")}</li>)}</ul>
          <small>解釈の詳細と指摘内容は実行証跡に保存しています。要件不足・矛盾を検知した場合は停止します。</small>
        </details>}
        <ul className="operator-children">{progress.children.map(c => <li key={c.id}><strong>{c.id} · Issue #{c.issue_id}</strong> — {text(c.status)} <Link url={c.issue_url} label="Issue" /> <Link url={c.pr_url} label="PR" />{c.run_id && <small>Run: {c.run_id}</small>}</li>)}</ul>
        <details><summary>判断・停止理由の履歴</summary><ol>{progress.decisions.map((d, i) => <li key={i}>{new Date(d.at).toLocaleString("ja-JP")} · {text(d.code)}</li>)}</ol></details>
        {progress.status === "stopped" && <p>同じ設定で再開しても、自動再送や予算のリセットは行いません。</p>}</div>}
      <h3>操作履歴</h3>{!jobs.length && <p>まだ実行していません。</p>}{jobs.slice(0, 20).map(j => <article key={j.id} className="operator-job">
        <strong>{profiles.find(p => p.id === j.profile_id)?.name || "登録設定"} · {j.action} · {text(j.status)}</strong><small>{new Date(j.created_at).toLocaleString("ja-JP")} · {j.id.slice(0, 12)}</small>
        {j.result && <p>{text(j.result.reason || j.result.status)}</p>}{active(j) && <button type="button" disabled={busy || j.stop_requested} onClick={() => void stop(j)}>{j.stop_requested ? "停止要求済み" : "停止を要求"}</button>}
        {j.status === "interrupted" && <p>実行記録を照合してから再開します。結果不明の推論・書き込みは再送しません。</p>}
        {j.status === "stopped" && <p>停止した試行は終了扱いになる場合があります。判断履歴を確認してください。</p>}
        <details><summary>操作の証跡</summary><ul>{j.events.map((e, i) => <li key={i}>{text(e.code)}</li>)}</ul></details>
      </article>)}
    </>}
  </section>;
}
