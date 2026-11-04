import { useEffect, useState } from "react";

type ApiState = "loading" | "connected" | "offline";

export default function App() {
  const [state, setState] = useState<ApiState>("loading");
  const [runtimes, setRuntimes] = useState<string[]>([]);
  const [error, setError] = useState("");

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
        <nav aria-label="Main navigation"><a className="selected" href="#overview">▦　概要</a><a href="#runtimes">◈　AI Runtime</a><span className="disabled">☷　タスク管理 <em>準備中</em></span><span className="disabled">⑂　実行履歴 <em>準備中</em></span></nav>
        <div className="sidebar-footer">Factory Core / Local</div>
      </aside>
      <main>
        <header><div><span className="eyebrow">DASHBOARD / OVERVIEW</span><h1 id="overview">工場ダッシュボード</h1><p>AI開発工場の接続状況とRuntimeを確認できます。</p></div><span className={"status " + state}>{state === "connected" ? "● API接続中" : state === "loading" ? "◌ 接続確認中" : "● API未接続"}</span></header>
        <section className="metrics" aria-label="Summary">
          <article className="metric"><span>API STATUS</span><strong>{state === "connected" ? "Online" : state === "loading" ? "Checking" : "Offline"}</strong><small>localhost:8000</small></article>
          <article className="metric"><span>REGISTERED RUNTIMES</span><strong>{state === "connected" ? runtimes.length : "—"}</strong><small>登録済みのアダプタ</small></article>
          <article className="metric"><span>ACTIVE TASKS</span><strong>—</strong><small>次のPRで対応予定</small></article>
        </section>
        <section className="panel" id="runtimes"><div className="panel-head"><div><span className="eyebrow">AGENT ADAPTERS</span><h2>AI Runtime</h2><p>登録されているRuntimeの一覧。実行可能・認証済みを意味しません。</p></div></div>
          {state === "loading" ? <p role="status">読み込み中...</p> : state === "offline" ? <div role="alert" className="notice">ローカルAPIに接続できません。FastAPIを起動してください。{error && <small>詳細: {error}</small>}</div> : <div className="runtime-list">{runtimes.map(name => <div className="runtime" key={name}><span className="runtime-symbol">◇</span><span><strong>{name}</strong><small>Registered adapter</small></span><span className="tag">登録済み</span></div>)}</div>}
        </section>
        <footer>Software Factory · ローカル管理画面 MVP · 操作機能は今後追加</footer>
      </main>
    </div>
  );
}
