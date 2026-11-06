import { useEffect, useState } from "react";

const plannedRuntimes = [
  { name: "Claude Code", key: "claude", note: "Anthropic · CLI Adapter候補" },
  { name: "Gemini CLI", key: "gemini", note: "Google · CLI Adapter候補" },
  { name: "Custom Agent", key: "custom", note: "OpenAI Agents SDK等 · 将来の拡張候補" },
] as const;

type ApiState = "loading" | "connected" | "offline";
type Project = { id: string; name: string; owner_id: string };
type Repository = { id: string; project_id: string; provider_id: string; external_id: string; visibility: string };
type Task = { id: string; prompt: string; created_at: string; provider?: string | null; instance?: string | null; bound_repository?: string | null; bound_local_path?: string | null; external_id?: string | null; external_url?: string | null };
type Issue = { repository: string; number: string; prompt: string; url: string };
type Run = { id: string; task_id: string; runtime: string; status: string; started_at: string };

export default function App() {
  const [state, setState] = useState<ApiState>("loading");
  const [quickRepo, setQuickRepo] = useState<string | null>(null);
  const [quickRepoLoading, setQuickRepoLoading] = useState(true);
  const [quickRepoPath, setQuickRepoPath] = useState("");
  const [quickRepoError, setQuickRepoError] = useState("");
  const [quickRepoBusy, setQuickRepoBusy] = useState(false);
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState("");
  const [projectRepos, setProjectRepos] = useState<Repository[]>([]);
  const [projectError, setProjectError] = useState("");
  const [projectLoading, setProjectLoading] = useState(false);
  const [projectsError, setProjectsError] = useState("");
  const [projectName, setProjectName] = useState("");
  const [projectBusy, setProjectBusy] = useState(false);
  const [projectMessage, setProjectMessage] = useState("");
  const [repoProvider, setRepoProvider] = useState("local-git");
  const [repoLocation, setRepoLocation] = useState("");
  const [repoVisibility, setRepoVisibility] = useState("local");
  const [repoBusy, setRepoBusy] = useState(false);
  const [repoMessage, setRepoMessage] = useState("");
  const [runtimes, setRuntimes] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [tasks, setTasks] = useState<Task[]>([]);
  const [newTask, setNewTask] = useState("");
  const [taskBusy, setTaskBusy] = useState(false);
  const [taskMessage, setTaskMessage] = useState("");
  const [bindingTaskId, setBindingTaskId] = useState("");
  const [runs, setRuns] = useState<Run[]>([]);
  const [repository, setRepository] = useState("KOHEIITOH/generic-software-factory");
  const [githubRepositories, setGithubRepositories] = useState<{full_name:string;can_push:boolean}[]>([]);
  const [githubRepoMessage, setGithubRepoMessage] = useState("");
  const [demoPrBusy, setDemoPrBusy] = useState(false);
  const [demoPrMessage, setDemoPrMessage] = useState("");
  const [demoPrUrl, setDemoPrUrl] = useState("");
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

  useEffect(() => {
    if (!selectedProject) { setProjectRepos([]); setProjectError(""); setProjectLoading(false); return; }
    const controller = new AbortController();
    setProjectRepos([]); setProjectError(""); setProjectLoading(true);
    void fetch("/api/projects/" + encodeURIComponent(selectedProject) + "/repositories", { signal: controller.signal })
      .then(async response => { if (!response.ok) throw new Error("Repository一覧を取得できませんでした"); return response.json(); })
      .then(data => { if (!controller.signal.aborted) setProjectRepos(data.repositories as Repository[]); })
      .catch(error => { if (!controller.signal.aborted) setProjectError(error instanceof Error ? error.message : "取得エラー"); })
      .finally(() => { if (!controller.signal.aborted) setProjectLoading(false); });
    return () => controller.abort();
  }, [selectedProject]);

  async function createProject() {
    if (!projectName.trim() || projectBusy) return;
    setProjectBusy(true); setProjectMessage("");
    try {
      const response = await fetch("/api/projects", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: projectName.trim() }),
      });
      if (!response.ok) throw new Error("Projectの登録に失敗しました（" + response.status + "）");
      const created: Project = await response.json();
      setProjects(previous => [...previous, created]);
      setSelectedProject(created.id);
      setProjectName("");
      setProjectsError("");
      setProjectMessage("Projectを登録しました。Repositoryを追加できます。");
    } catch (cause) {
      setProjectMessage(cause instanceof Error ? cause.message : "登録エラー");
    } finally { setProjectBusy(false); }
  }

  async function createRepository() {
    if (!selectedProject || !repoLocation.trim() || !repoProvider.trim() || repoBusy) return;
    setRepoBusy(true); setRepoMessage("");
    const target = selectedProject;
    try {
      const response = await fetch("/api/projects/" + encodeURIComponent(target) + "/repositories", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider_id: repoProvider.trim(), external_id: repoLocation.trim(), visibility: repoVisibility,
        }),
      });
      if (!response.ok) throw new Error(response.status === 409
        ? "このRepositoryはすでに登録されています。" : "Repositoryの登録に失敗しました（" + response.status + "）");
      const created: Repository = await response.json();
      if (target === selectedProject) {
        setProjectRepos(previous => [...previous, created]);
        setRepoLocation("");
        setProjectError("");
        setRepoMessage("Repositoryを登録しました。");
      }
    } catch (cause) {
      setRepoMessage(cause instanceof Error ? cause.message : "登録エラー");
    } finally { setRepoBusy(false); }
  }

  useEffect(() => {
    const controller = new AbortController();
    void fetch("/api/quick/repository", { signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw new Error("Repositoryを検出できませんでした");
        return response.json();
      })
      .then(data => {
        if (!controller.signal.aborted) {
          setQuickRepo(data.detected && typeof data.repository_root === "string"
            ? data.repository_root : null);
        }
      })
      .catch(() => { if (!controller.signal.aborted) setQuickRepo(null); })
      .finally(() => { if (!controller.signal.aborted) setQuickRepoLoading(false); });
    return () => controller.abort();
  }, []);

  async function inspectQuickRepository() {
    if (!quickRepoPath.trim() || quickRepoBusy) return;
    setQuickRepoBusy(true); setQuickRepoError("");
    try {
      const response = await fetch("/api/quick/repository/inspect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: quickRepoPath.trim() }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === "string"
        ? data.detail : "Gitリポジトリを確認できませんでした");
      setQuickRepo(data.repository_root);
      setQuickRepoPath(data.repository_root);
    } catch (cause) {
      setQuickRepoError(cause instanceof Error ? cause.message : "確認エラー");
    } finally { setQuickRepoBusy(false); }
  }

  async function createLocalTask() {
    if (!newTask.trim() || taskBusy) return;
    setTaskBusy(true); setTaskMessage("");
    try {
      const response = await fetch("/api/tasks", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: newTask.trim() }),
      });
      if (!response.ok) throw new Error("タスクの作成に失敗しました。");
      const data = await response.json();
      setTaskMessage("タスクを登録しました: " + data.task_id + "（AIは実行されません）");
      setNewTask("");
      const refreshed = await fetch("/api/tasks");
      if (refreshed.ok) setTasks((await refreshed.json()).tasks);
    } catch (cause) {
      setTaskMessage(cause instanceof Error ? cause.message : "作成エラー");
    } finally { setTaskBusy(false); }
  }

  async function loadGithubRepositories() {
    setGithubRepoMessage("取得中...");
    try {
      const response = await fetch("/api/github/repositories");
      if (!response.ok) throw new Error(response.status === 503 ? "GitHub認証情報が未設定です" : "リポジトリ一覧を取得できませんでした");
      const data = await response.json();
      setGithubRepositories(data.repositories);
      setGithubRepoMessage(data.repositories.length ? "" : "利用可能なリポジトリがありません");
    } catch (error) {
      setGithubRepoMessage(error instanceof Error ? error.message : "取得エラー");
    }
  }

  async function createDemoPR() {
    if (demoPrBusy || !githubRepositories.some(item => item.full_name === repository && item.can_push)) return;
    if (!window.confirm(repository + " にデモ用のブランチとDraft PRを作成します。アプリコードは変更しません。実行しますか？")) return;
    setDemoPrBusy(true); setDemoPrMessage(""); setDemoPrUrl("");
    try {
      const response = await fetch("/api/github/demo/draft-pr", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ repository, confirmed: true }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "PR作成に失敗しました");
      setDemoPrUrl(data.url);
      setDemoPrMessage("Draft PR #" + data.number + " を作成しました");
    } catch (error) {
      setDemoPrMessage(error instanceof Error ? error.message : "PR作成エラー");
    } finally { setDemoPrBusy(false); }
  }

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

  async function bindTaskRepository(task: Task) {
    if (!quickRepo) return;
    setBindingTaskId(task.id);
    setTaskMessage("");
    try {
      const response = await fetch("/api/tasks/" + encodeURIComponent(task.id) + "/repository", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ repository: task.instance ?? "", local_path: quickRepo }),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(typeof body.detail === "string" ? body.detail : "Repository紐付けに失敗しました");
      }
      const data = await response.json();
      setTasks(previous => previous.map(item => item.id === task.id ? { ...item, bound_repository: data.repository, bound_local_path: data.local_path } : item));
      setTaskMessage("Repository紐付け完了。AI実行はまだ行われません。");
    } catch (error) {
      setTaskMessage(error instanceof Error ? error.message : "紐付けエラー");
    } finally {
      setBindingTaskId("");
    }
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

  useEffect(() => {
    const controller = new AbortController();
    void fetch("/api/projects", { signal: controller.signal })
      .then(async response => { if (!response.ok) throw new Error("Project一覧を取得できませんでした"); return response.json(); })
      .then(data => {
        if (!data || !Array.isArray(data.projects) || !data.projects.every((p: unknown) => p && typeof p === "object" && "id" in p && typeof p.id === "string" && "name" in p && typeof p.name === "string")) throw new Error("Project APIの応答が不正です");
        if (!controller.signal.aborted) setProjects(data.projects as Project[]);
      })
      .catch(error => { if (!controller.signal.aborted) setProjectsError(error instanceof Error ? error.message : "取得エラー"); });
    return () => controller.abort();
  }, []);

  const activeRuns = runs.filter(run => run.status === "running").length;
  const linkedTasks = tasks.filter(task => task.provider).length;
  const formatDate = (date: string) => Number.isNaN(Date.parse(date)) ? date : new Date(date).toLocaleString("ja-JP");

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="brand"><span className="brand-icon">SF</span><span>Software Factory<small>DEVELOPMENT CONTROL CENTER</small></span></div>
        <nav aria-label="Main navigation"><a className="selected" href="#overview">▦　概要</a><a href="#quick-start">▶　クイック開始</a><a href="#projects">▤　Project</a><a href="#runtimes">◈　AI Runtime</a><a href="#tasks">☷　タスク一覧</a><a href="#github-import">＋　Issue取り込み</a><a href="#runs">⑂　実行履歴</a><span className="nav-group-label">DOCUMENTATION</span><a href="/guide">▤　ユーザーガイド</a><a href="/onboarding">↗　オンボーディング</a></nav>
        <div className="sidebar-footer"><span className="sidebar-dot" /> LOCAL WORKSPACE <small>Factory Core · v0.1</small></div>
      </aside>
      <main>
        <header><div><h1 id="overview">Software Factory</h1><p>開発対象を選んで、タスクを管理します。</p></div><span role="status" className={"status " + state}>{state === "connected" ? "● ローカルAPI接続中" : state === "loading" ? "◌ 接続確認中" : "● API未接続"}</span></header>
        <section className="metrics" aria-label="Summary">
          <article className="metric"><span>接続状態</span><strong>{state === "connected" ? "Online" : state === "loading" ? "Checking" : "Offline"}</strong><small>localhost:8000</small></article>
          <article className="metric"><span>登録済みAI Runtime</span><strong>{state === "connected" ? runtimes.length : "—"}</strong><small>登録済みのアダプタ</small></article>
          <article className="metric"><span>実行中のRun</span><strong>{state === "connected" ? activeRuns : "—"}</strong><small>実行中のRun</small></article>
        </section>
        <section className="panel quick-start-panel" id="quick-start">
          <div className="panel-head"><h2>クイック開始</h2><p>開発対象のGitリポジトリを指定してください。Project登録は不要です。</p></div>
          <form className="issue-form" onSubmit={event => { event.preventDefault(); void inspectQuickRepository(); }}>
            <label>Repositoryのパス<input aria-label="クイック開始のRepositoryパス" value={quickRepoPath} onChange={event => { setQuickRepoPath(event.target.value); setQuickRepo(null); setQuickRepoError(""); }} placeholder="/Users/you/projects/my-service" /></label>
            <button type="submit" disabled={!quickRepoPath.trim() || quickRepoBusy}>{quickRepoBusy ? "確認中..." : "確認"}</button>
          </form>
          {quickRepoLoading ? <p role="status">Gitを確認中...</p> : quickRepo
            ? <p className="quick-repo-status">検証済み（Task未連携）: <code>{quickRepo}</code></p>
            : <p role="status">開発対象のパスを入力して確認してください。</p>}
          {quickRepoError && <p role="alert">{quickRepoError}</p>}
          <a className="source-link quick-start-link" href="#tasks">Taskを作成する ↓</a>
          <p className="quick-start-note">※ 現在はRepository確認とTask登録まで。AI実行は未対応です。</p>
        </section>
        <div className="section-heading"><div><span className="eyebrow">FACTORY WORKSPACE</span><h2>ワークスペース</h2></div><span className="section-note">タスク {tasks.length}件 · 外部連携 {linkedTasks}件</span></div><section className="panel" id="projects">
          <div className="panel-head"><span className="eyebrow">LOCAL PROJECTS</span><h2>Project・Repository</h2><p>複数Repositoryをまとめる場合に登録します。単一RepositoryのTask作成には登録不要です。登録だけではGit操作・AI実行は始まりません。</p></div>
          <form className="issue-form" onSubmit={event => { event.preventDefault(); void createProject(); }}>
            <label>新しいProject名<input aria-label="新しいProject名" maxLength={120} value={projectName} onChange={event => setProjectName(event.target.value)} placeholder="例: My Service" /></label>
            <button type="submit" disabled={projectBusy || !projectName.trim() || state !== "connected"}>{projectBusy ? "登録中..." : "Projectを登録"}</button>
          </form>
          {projectMessage && <p role="status">{projectMessage}</p>}
          {projectsError && <p role="alert">{projectsError}</p>}
          {state === "connected" && (projects.length ? <>
            <label className="project-selector">Projectを選択<select aria-label="Projectを選択" value={selectedProject} onChange={event => { setSelectedProject(event.target.value); setRepoMessage(""); }}><option value="">選択してください</option>{projects.map(project => <option key={project.id} value={project.id}>{project.name}</option>)}</select></label>
            {selectedProject && <>
              <form className="issue-form project-register-form" onSubmit={event => { event.preventDefault(); void createRepository(); }}>
                <label>接続先<select aria-label="Repositoryの接続先" value={repoProvider} onChange={event => { setRepoProvider(event.target.value); setRepoVisibility(event.target.value === "local-git" ? "local" : "private"); }}><option value="local-git">ローカルGit</option><option value="github">GitHub（メタデータ登録のみ）</option></select></label>
                <label>{repoProvider === "local-git" ? "Repositoryのパス" : "Repository（owner/repo）"}<input aria-label="Repositoryの場所" maxLength={500} value={repoLocation} onChange={event => setRepoLocation(event.target.value)} placeholder={repoProvider === "local-git" ? "/path/to/repository" : "owner/repo"} /></label>
                <label>公開範囲<select aria-label="公開範囲" value={repoVisibility} onChange={event => setRepoVisibility(event.target.value)}><option value="local">local</option><option value="private">private</option><option value="public">public</option></select></label>
                <button type="submit" disabled={repoBusy || projectLoading || !repoLocation.trim() || state !== "connected"}>{repoBusy ? "登録中..." : "Repositoryを追加"}</button>
              </form>
              {repoMessage && <p role="status">{repoMessage}</p>}
              {projectError ? <p role="alert">{projectError}</p> : projectLoading ? <p role="status">Repositoryを読み込み中...</p> : projectRepos.length ? <div className="runtime-list">{projectRepos.map(repo => <div className="runtime" key={repo.id}><span><strong>{repo.external_id}</strong><small>{repo.provider_id} · {repo.visibility}</small></span></div>)}</div> : <p>Repositoryはまだ登録されていません。</p>}
            </>}
          </> : !projectsError && <p>Projectはまだ登録されていません。上のフォームから追加できます。</p>)}
        </section><section className="panel" id="runtimes"><div className="panel-head"><div><span className="eyebrow">AGENT ADAPTERS</span><h2>AI Runtime</h2><p>登録済みAdapterと今後の対応候補です。登録済みでも実行可能・認証済みを意味しません。</p></div></div>
          {state === "loading" ? <p role="status">読み込み中...</p> : state === "offline" ? <div role="alert" className="notice">ローカルAPIに接続できません。FastAPIを起動してください。{error && <small>詳細: {error}</small>}</div> : <div className="runtime-list">{runtimes.map(name => <div className="runtime" key={name}><span className="runtime-symbol">◇</span><span><strong>{name}</strong><small>Registered adapter</small></span><span className="tag">登録済み</span></div>)}{plannedRuntimes.filter(candidate => !runtimes.includes(candidate.key)).map(candidate => <div className="runtime planned-runtime" key={candidate.key}><span className="runtime-symbol">◇</span><span><strong>{candidate.name}</strong><small>{candidate.note} · 利用不可</small></span><span className="tag planned-tag">未登録</span></div>)}</div>}
        </section>
        <section className="panel" id="github-import">
          <div className="panel-head"><span className="eyebrow">GITHUB ISSUES</span><h2>GitHub Issueを取り込む</h2><p>GitHub Issueを確認してから登録します。Private Repositoryはサーバー側の認証設定が必要です。AIは自動実行されません。</p></div>
          <div className="issue-form"><button type="button" onClick={() => void loadGithubRepositories()}>GitHubのリポジトリ一覧を取得</button>{githubRepositories.length > 0 && <label>リポジトリを選択<select aria-label="GitHubリポジトリを選択" value={repository} onChange={event => {setRepository(event.target.value);setIssuePreview(null);setIssueList([]);}}><option value="">選択してください</option>{githubRepositories.map(item => <option key={item.full_name} value={item.full_name}>{item.full_name}{item.can_push ? "（Push可能）" : "（読み取りのみ）"}</option>)}</select></label>}{githubRepoMessage && <p role="status">{githubRepoMessage}</p>}</div>
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
              {issueListBusy ? "取得中..." : "Issue一覧を表示"}
            </button>
          </div>
          {issueListMessage && <p role="status">{issueListMessage}</p>}
          {issueList.length > 0 && <div className="runtime-list" aria-label="GitHub Issue一覧">
            {issueList.map(issue => <div className="runtime" key={issue.number}>
              <span><strong>#{issue.number} · {issue.prompt.split("\n")[0]}</strong></span>
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
        <section className="panel" id="tasks"><div className="panel-head"><span className="eyebrow">TASK TRACKER</span><h2>タスク一覧</h2><p>ローカルTaskを登録できます。登録してもAIは自動実行されません。</p></div><form className="issue-form" onSubmit={event => {event.preventDefault(); void createLocalTask();}}><label>新しいタスク<textarea aria-label="新しいタスク" value={newTask} maxLength={10000} onChange={event => setNewTask(event.target.value)} placeholder="AIに依頼したい作業を入力" rows={3} /></label><button type="submit" disabled={taskBusy || !newTask.trim() || state !== "connected"}>{taskBusy ? "登録中..." : "タスクを登録"}</button></form>{taskMessage && <p role="status">{taskMessage}</p>}{state === "connected" && (tasks.length ? <div className="runtime-list">{tasks.map(task => <div className="runtime" key={task.id}><span><strong>{task.prompt}</strong><small>{task.provider ? `${task.provider.toUpperCase()} · ${task.external_id ?? ""} · ` : "LOCAL · "}{formatDate(task.created_at)}</small></span>{task.provider === "github" && <button type="button" disabled={!quickRepo || bindingTaskId !== "" || !task.instance} onClick={() => void bindTaskRepository(task)}>{bindingTaskId === task.id ? "確認中..." : task.bound_repository && task.bound_local_path === quickRepo ? "紐付け済み" : "Repositoryを紐付け"}</button>}{task.external_url && <a className="source-link" href={task.external_url} target="_blank" rel="noopener noreferrer" aria-label="元Issueを開く">元Issue ↗</a>}</div>)}</div> : <p>まだタスクはありません。CLIまたは外部Issue連携から取り込むと、ここに表示されます。</p>)}</section>
        <section className="panel" id="runs"><div className="panel-head"><span className="eyebrow">EXECUTION HISTORY</span><h2>実行履歴</h2><p>直近の実行状態を表示します。自動更新・実行操作は今後追加します。</p></div>{state === "connected" && (runs.length ? <div className="runtime-list">{runs.map(run => <div className="runtime" key={run.id}><span><strong>{run.runtime} · {run.status}</strong><small>{run.id.slice(0, 12)} · {formatDate(run.started_at)}</small></span></div>)}</div> : <p>まだ実行履歴はありません。AI Runtimeで実行すると、ここに記録されます。</p>)}</section>
        <footer>Software Factory · ローカル管理画面 MVP · 操作機能は今後追加</footer>
      </main>
    </div>
  );
}
