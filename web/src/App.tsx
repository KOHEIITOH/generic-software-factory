import { useEffect, useState } from "react";

type ApiState = "loading" | "connected" | "offline";
type Task = { id: string; prompt: string; created_at: string };
type Run = { id: string; task_id: string; runtime: string; status: string; started_at: string };

export default function App() {
  const [state, setState] = useState<ApiState>("loading");
  const [runtimes, setRuntimes] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [tasks, setTasks] = useState<Task[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);

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

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="brand"><span className="brand-icon">SF</span><span>Software Factory<small>LOCAL CONTROL CENTER</small></span></div>
        <nav aria-label="Main navigation"><a className="selected" href="#overview">▦　概要</a><a href="#runtimes">◈　AI Runtime</a><a href="#tasks">☷　タスク一覧</a><a href="#runs">⑂　実行履歴</a></nav>
        <div className="sidebar-footer">Factory Core / Local</div>
      </aside>
      <main>
        <header><div><span className="eyebrow">DASHBOARD / OVERVIEW</span><h1 id="overview">工場ダッシュボード</h1><p>AI開発工場の接続状況とRuntimeを確認できます。</p></div><span className={"status " + state}>{state === "connected" ? "● API接続中" : state === "loading" ? "◌ 接続確認中" : "● API未接続"}</span></header>
        <section className="metrics" aria-label="Summary">
          <article className="metric"><span>API STATUS</span><strong>{state === "connected" ? "Online" : state === "loading" ? "Checking" : "Offline"}</strong><small>localhost:8000</small></article>
          <article className="metric"><span>REGISTERED RUNTIMES</span><strong>{state === "connected" ? runtimes.length : "—"}</strong><small>登録済みのアダプタ</small></article>
          <article className="metric"><span>ACTIVE TASKS</span><strong>{state === "connected" ? runs.filter(run => run.status === "running").length : "—"}</strong><small>実行中のRun</small></article>
        </section>
        <section className="panel" id="runtimes"><div className="panel-head"><div><span className="eyebrow">AGENT ADAPTERS</span><h2>AI Runtime</h2><p>登録されているRuntimeの一覧。実行可能・認証済みを意味しません。</p></div></div>
          {state === "loading" ? <p role="status">読み込み中...</p> : state === "offline" ? <div role="alert" className="notice">ローカルAPIに接続できません。FastAPIを起動してください。{error && <small>詳細: {error}</small>}</div> : <div className="runtime-list">{runtimes.map(name => <div className="runtime" key={name}><span className="runtime-symbol">◇</span><span><strong>{name}</strong><small>Registered adapter</small></span><span className="tag">登録済み</span></div>)}</div>}
        </section>
        <section className="panel" id="tasks"><div className="panel-head"><span className="eyebrow">TASK TRACKER</span><h2>タスク一覧</h2><p>CLIなどで登録したタスクを読み取り専用で表示します。</p></div>{state === "connected" && (tasks.length ? <div className="runtime-list">{tasks.map(task => <div className="runtime" key={task.id}><span><strong>{task.prompt}</strong><small>{task.id.slice(0, 12)} · {task.created_at}</small></span></div>)}</div> : <p>まだタスクはありません。</p>)}</section>
        <section className="panel" id="runs"><div className="panel-head"><span className="eyebrow">EXECUTION HISTORY</span><h2>実行履歴</h2><p>直近の実行状態を表示します。自動更新・実行操作は今後追加します。</p></div>{state === "connected" && (runs.length ? <div className="runtime-list">{runs.map(run => <div className="runtime" key={run.id}><span><strong>{run.runtime} · {run.status}</strong><small>{run.id.slice(0, 12)} · {run.started_at}</small></span></div>)}</div> : <p>まだ実行履歴はありません。</p>)}</section>
        <footer>Software Factory · ローカル管理画面 MVP · 操作機能は今後追加</footer>
      </main>
    </div>
  );
}
