import { useEffect, useState } from "react";

const plannedRuntimes = [
  { name: "Claude Code", key: "claude", note: "Anthropic · CLI Adapter候補" },
  { name: "Gemini CLI", key: "gemini", note: "Google · CLI Adapter候補" },
  { name: "Custom Agent", key: "custom", note: "OpenAI Agents SDK等 · 将来の拡張候補" },
] as const;

type ApiState = "loading" | "connected" | "offline";
type Task = { id: string; prompt: string; created_at: string; provider?: string | null; external_id?: string | null; external_url?: string | null };
type Issue = { repository: string; number: string; prompt: string; url: string };
type Run = { id: string; task_id: string; runtime: string; status: string; started_at: string };

export default function App() {
  const [state, setState] = useState<ApiState>("loading");
  const [runtimes, setRuntimes] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [tasks, setTasks] = useState<Task[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [repository, setRepository] = useState("KOHEIITOH/generic-software-factory");
  const [issueNumber, setIssueNumber] = useState("");
  const [issuePreview, setIssuePreview] = useState<{ repository: string; number: string; prompt: string; url: string } | null>(null);
  const [issueList, setIssueList] = useState<Issue[]>([]);
  const [issuePage, setIssuePage] = useState(0);
  const [issueHasMore, setIssueHasMore] = useState(false);
  const [issueState, setIssueState] = useState<"open" | "closed">("open");
  const [issueListBusy, setIssueListBusy] = useState(false);
  const [issueListMessage, setIssueListMessage] = useState("");
  const [issueBusy, setIssueBusy] = useState(false);
  const [issueMessage, setIssueMessage] = useState("");

  async function loadIssues(page = 1) {
    if (issueListBusy) return;
    setIssueListBusy(true); setIssueListMessage("");
    if (page === 1) { setIssueList([]); setIssuePreview(null); setIssueHasMore(false); }
    try {
      const params = new URLSearchParams({ repository: repository.trim(), page: String(page), state: issueState });
      const response = await fetch("/api/github/issues?" + params);
      if (!response.ok) throw new Error("Issue一覧を取得できませんでした。公開リポジトリか確認してください。");
      const data = await response.json();
      setIssueList(previous => page === 1 ? data.issues : [...previous, ...data.issues]);
      setIssuePage(page);
      setIssueHasMore(data.has_more);
      if (page === 1 && data.issues.length === 0 && !data.has_more) setIssueListMessage("該当するIssueは見つかりませんでした。");
    } catch (error) {
      setIssueListMessage(error instanceof Error ? error.message : "取得エラー");
    } finally { setIssueListBusy(false); }
  }

  async function previewIssue() {
    setIssueBusy(true); setIssueMessage(""); setIssuePreview(null);
    try {
      const params = new URLSearchParams({ repository: repository.trim(), number: issueNumber.trim() });
      const response = await fetch("/api/github/issue?" + params);
      if (!response.ok) throw new Error("Issueを取得できませんでした。リポジトリと番号を確認してください。");
      const data = await response.json();
      setIssuePreview(data.issue);
    } catch (error) { setIssueMessage(error instanceof Error ? error.message : "取得エラー"); }
    finally { setIssueBusy(false); }
  }

  async function importIssue() {
    if (!issuePreview) return;
    setIssueBusy(true); setIssueMessage("");
    try {
      const response = await fetch("/api/github/import", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ repository: issuePreview.repository, number: Number(issuePreview.number) }),
      });
      if (!response.ok) throw new Error("取り込みに失敗しました。");
      const data = await response.json();
      setIssueMessage("取り込み完了: Task " + data.task_id);
      setIssuePreview(null);
      const tasksResponse = await fetch("/api/tasks");
      if (tasksResponse.ok) setTasks((await tasksResponse.json()).tasks);
    } catch (error) { setIssueMessage(error instanceof Error ? error.message : "取り込みエラー"); }
    finally { setIssueBusy(false); }
  }

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      try {
        const [health, available] = await Promise.all([
          fetch("/api/health", { signal: controller.signal }),
          fetch("/api/runtimes", { signal: controller.signal }),
        ]);
        if (!health.ok || !available.ok) throw new Error("API returned an error");
        const payload: unknown = await available.json();
        if (!payload || typeof payload !== "object" || !("runtimes" in payload)
          || !Array.isArray(payload.runtimes)
          || !payload.runtimes.every((item: unknown) => typeof item === "string")) {
          throw new Error("Unexpected runtime response");
        }
        setRuntimes(payload.runtimes as string[]);
        const [taskResponse, runResponse] = await Promise.all([
          fetch("/api/tasks", { signal: controller.signal }),
          fetch("/api/runs", { signal: controller.signal }),
        ]);
        if (!taskResponse.ok || !runResponse.ok) throw new Error("Task API returned an error");
        const taskData: unknown = await taskResponse.json();
        const runData: unknown = await runResponse.json();
        if (!taskData || typeof taskData !== "object" || !("tasks" in taskData) || !Array.isArray(taskData.tasks)
          || !taskData.tasks.every((item: unknown) => item && typeof item === "object" && "id" in item && typeof item.id === "string" && "prompt" in item && typeof item.prompt === "string")) throw new Error("Unexpected tasks response");
        if (!runData || typeof runData !== "object" || !("runs" in runData) || !Array.isArray(runData.runs)
          || !runData.runs.every((item: unknown) => item && typeof item === "object" && "id" in item && typeof item.id === "string" && "status" in item && typeof item.status === "string")) throw new Error("Unexpected runs response");
        setTasks(taskData.tasks as Task[]);
        setRuns(runData.runs as Run[]);
        setState("connected");
      } catch (cause) {
        if (controller.signal.aborted) return;
        setError(cause instanceof Error ? cause.message : "Unknown error");
        setState("offline");
      }
    }
    void load();
    return () => controller.abort();
  }, []);

  const activeRuns = runs.filter(run => run.status === "running").length;
  const linkedTasks = tasks.filter(task => task.provider).length;
  const formatDate = (date: string) => Number.isNaN(Date.parse(date)) ? date : new Date(date).toLocaleString("ja-JP");

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="brand"><span className="brand-icon">SF</span><span>Software Factory<small>DEVELOPMENT CONTROL CENTER</small></span></div>
        <nav aria-label="Main navigation"><a className="selected" href="#overview">▦　概要</a><a href="#runtimes">◈　AI Runtime</a><a href="#tasks">☷　タスク一覧</a><a href="#github-import">＋　Issue取り込み</a><a href="#runs">⑂　実行履歴</a><span className="nav-group-label">DOCUMENTATION</span><a href="/guide">▤　ユーザーガイド</a><a href="/onboarding">↗　オンボーディング</a></nav>
        <div className="sidebar-footer"><span className="sidebar-dot" /> LOCAL WORKSPACE <small>Factory Core · v0.1</small></div>
      </aside>
      <main>
        <header><div><span className="eyebrow">OVERVIEW / WORKSPACE</span><h1 id="overview">開発コントロールセンター <span className="title-spark">✦</span></h1><p>AIによる開発タスクと実行状況を、ひとつの画面で。</p></div><span role="status" className={"status " + state}>{state === "connected" ? "● ローカルAPI接続中" : state === "loading" ? "◌ 接続確認中" : "● API未接続"}</span></header><div className="hero-banner"><div><span className="eyebrow">SOFTWARE FACTORY / LOCAL</span><h2>アイデアから、実装へ。</h2><p>タスクの取り込みからAI開発・品質確認まで。現在は閲覧専用のダッシュボードです。</p></div><span className="hero-mark" aria-hidden="true">⌘</span></div>
        <section className="metrics" aria-label="Summary">
          <article className="metric"><span>接続状態</span><strong>{state === "connected" ? "Online" : state === "loading" ? "Checking" : "Offline"}</strong><small>localhost:8000</small></article>
          <article className="metric"><span>登録済みAI Runtime</span><strong>{state === "connected" ? runtimes.length : "—"}</strong><small>登録済みのアダプタ</small></article>
          <article className="metric"><span>実行中のRun</span><strong>{state === "connected" ? activeRuns : "—"}</strong><small>実行中のRun</small></article>
        </section>
        <div className="section-heading"><div><span className="eyebrow">FACTORY WORKSPACE</span><h2>ワークスペース</h2></div><span className="section-note">タスク {tasks.length}件 · 外部連携 {linkedTasks}件</span></div><section className="panel" id="runtimes"><div className="panel-head"><div><span className="eyebrow">AGENT ADAPTERS</span><h2>AI Runtime</h2><p>登録済みAdapterと今後の対応候補です。登録済みでも実行可能・認証済みを意味しません。</p></div></div>
          {state === "loading" ? <p role="status">読み込み中...</p> : state === "offline" ? <div role="alert" className="notice">ローカルAPIに接続できません。FastAPIを起動してください。{error && <small>詳細: {error}</small>}</div> : <div className="runtime-list">{runtimes.map(name => <div className="runtime" key={name}><span className="runtime-symbol">◇</span><span><strong>{name}</strong><small>Registered adapter</small></span><span className="tag">登録済み</span></div>)}{plannedRuntimes.filter(candidate => !runtimes.includes(candidate.key)).map(candidate => <div className="runtime planned-runtime" key={candidate.key}><span className="runtime-symbol">◇</span><span><strong>{candidate.name}</strong><small>{candidate.note} · 利用不可</small></span><span className="tag planned-tag">未登録</span></div>)}</div>}
        </section>
        <section className="panel" id="github-import">
          <div className="panel-head"><span className="eyebrow">GITHUB ISSUES</span><h2>GitHub Issueを取り込む</h2><p>公開リポジトリのIssueを確認してから登録します。AIは自動実行されません。</p></div>
          <div className="issue-form">
            <label>リポジトリ（owner/repo）<input value={repository} onChange={event => {setRepository(event.target.value); setIssuePreview(null); setIssueList([]); setIssueListMessage(""); setIssuePage(0); setIssueHasMore(false);}} placeholder="owner/repo" /></label>
            <label>Issue番号<input type="number" min="1" value={issueNumber} onChange={event => {setIssueNumber(event.target.value); setIssuePreview(null);}} placeholder="例: 12" /></label>
            <button type="button" disabled={issueBusy || !repository.trim() || !/^[1-9][0-9]*$/.test(issueNumber)} onClick={() => void previewIssue()}>内容を確認</button>
          </div>
          <div className="issue-form">
            <label>状態
              <select value={issueState} onChange={event => {
                setIssueState(event.target.value as "open" | "closed");
                setIssueList([]); setIssuePage(0); setIssueHasMore(false);
                setIssuePreview(null); setIssueListMessage("");
              }}>
                <option value="open">Open</option>
                <option value="closed">Closed</option>
              </select>
            </label>
            <button type="button" disabled={issueListBusy || issueBusy || !repository.trim()} onClick={() => void loadIssues()}>
              {issueListBusy ? "取得中..." : "公開Issue一覧を表示"}
            </button>
          </div>
          {issueListMessage && <p role="status">{issueListMessage}</p>}
          {issueList.length > 0 && <div className="runtime-list" aria-label="公開GitHub Issue一覧">
            {issueList.map(issue => <div className="runtime" key={issue.number}>
              <span><strong>#{issue.number} · {issue.prompt.split("\\n")[0]}</strong></span>
              <button type="button" disabled={issueBusy} onClick={() => {
                setIssueNumber(issue.number); setIssuePreview(issue); setIssueMessage("");
              }}>選択</button>
            </div>)}
          </div>}
          {issueHasMore && <div className="issue-form">
            <button type="button" disabled={issueListBusy} onClick={() => void loadIssues(issuePage + 1)}>
              {issueListBusy ? "読み込み中..." : "さらに読み込む"}
            </button>
          </div>}
          {issueMessage && <p role="status">{issueMessage}</p>}
          {issuePreview && <div className="issue-preview"><strong>Issue #{issuePreview.number}</strong><pre>{issuePreview.prompt}</pre><a className="source-link" href={issuePreview.url} target="_blank" rel="noopener noreferrer">GitHubで開く ↗</a><button type="button" disabled={issueBusy} onClick={() => void importIssue()}>このIssueを取り込む</button></div>}
        </section>
        <section className="panel" id="tasks"><div className="panel-head"><span className="eyebrow">TASK TRACKER</span><h2>タスク一覧</h2><p>CLIなどで登録したタスクを読み取り専用で表示します。</p></div>{state === "connected" && (tasks.length ? <div className="runtime-list">{tasks.map(task => <div className="runtime" key={task.id}><span><strong>{task.prompt}</strong><small>{task.provider ? `${task.provider.toUpperCase()} · ${task.external_id ?? ""} · ` : "LOCAL · "}{formatDate(task.created_at)}</small></span>{task.external_url && <a className="source-link" href={task.external_url} target="_blank" rel="noopener noreferrer" aria-label="元Issueを開く">元Issue ↗</a>}</div>)}</div> : <p>まだタスクはありません。CLIまたは外部Issue連携から取り込むと、ここに表示されます。</p>)}</section>
        <section className="panel" id="runs"><div className="panel-head"><span className="eyebrow">EXECUTION HISTORY</span><h2>実行履歴</h2><p>直近の実行状態を表示します。自動更新・実行操作は今後追加します。</p></div>{state === "connected" && (runs.length ? <div className="runtime-list">{runs.map(run => <div className="runtime" key={run.id}><span><strong>{run.runtime} · {run.status}</strong><small>{run.id.slice(0, 12)} · {formatDate(run.started_at)}</small></span></div>)}</div> : <p>まだ実行履歴はありません。AI Runtimeで実行すると、ここに記録されます。</p>)}</section>
        <footer>Software Factory · ローカル管理画面 MVP · 操作機能は今後追加</footer>
      </main>
    </div>
  );
}
