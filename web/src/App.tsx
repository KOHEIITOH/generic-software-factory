import { lazy, Suspense, useEffect, useState } from "react";
import OperatorPanel from "./OperatorPanel";

const ProjectPanel = lazy(() => import("./ProjectPanel"));
type ApiState = "loading" | "connected" | "offline";

export default function App() {
  const [state, setState] = useState<ApiState>("loading");
  const [projectsOpen, setProjectsOpen] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    void fetch("/api/health", { signal: controller.signal })
      .then(async response => {
        if (!response.ok || (await response.json()).status !== "ok") throw new Error("API unavailable");
        if (!controller.signal.aborted) setState("connected");
      })
      .catch(() => { if (!controller.signal.aborted) setState("offline"); });
    return () => controller.abort();
  }, []);

  return <div className="layout">
    <aside className="sidebar">
      <div className="brand"><span className="brand-icon">SF</span><span>Software Factory<small>DEVELOPMENT CONTROL CENTER</small></span></div>
      <nav aria-label="Main navigation"><a className="selected" href="#operator">▶　Issueを実行</a><a href="#workspace-details">▤　Project管理</a><span className="nav-group-label">DOCUMENTATION</span><a href="/guide">▤　ユーザーガイド</a><a href="/onboarding">↗　オンボーディング</a></nav>
      <div className="sidebar-footer"><span className="sidebar-dot" /> LOCAL WORKSPACE</div>
    </aside>
    <main>
      <header><div><h1>Software Factory</h1><p>Issueを選び、実装からDraft PRまで進めます。</p></div><span role="status" className={"status " + state}>{state === "connected" ? "● ローカルAPI接続中" : state === "loading" ? "◌ 接続確認中" : "● API未接続"}</span></header>
      {state === "offline" && <p role="alert">ローカルAPIに接続できません。起動したターミナルを確認してください。</p>}
      <OperatorPanel />
      <details id="workspace-details" className="workspace-details" onToggle={event => setProjectsOpen(event.currentTarget.open)}><summary>Project・Repository管理（任意）</summary>
        {projectsOpen && <Suspense fallback={<p role="status">Project管理を読み込み中…</p>}><ProjectPanel connected={state === "connected"} /></Suspense>}
      </details>
      <footer>Software Factory · Issue → Draft PR</footer>
    </main>
  </div>;
}
