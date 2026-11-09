import { useEffect, useState } from "react";

type Project = { id: string; name: string; owner_id: string };
type Repository = { id: string; project_id: string; provider_id: string; external_id: string; visibility: string };

export default function ProjectPanel({ connected }: { connected: boolean }) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState("");
  const [projectRepos, setProjectRepos] = useState<Repository[]>([]);
  const [projectError, setProjectError] = useState("");
  const [projectLoading, setProjectLoading] = useState(false);
  const [projectsError, setProjectsError] = useState("");
  const [projectName, setProjectName] = useState("");
  const [projectBusy, setProjectBusy] = useState(false);
  const [projectMessage, setProjectMessage] = useState("");
  const [repoProvider, setRepoProvider] = useState("github");
  const [repoLocation, setRepoLocation] = useState("");
  const [repoVisibility, setRepoVisibility] = useState("private");
  const [repoBusy, setRepoBusy] = useState(false);
  const [repoMessage, setRepoMessage] = useState("");

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
    void fetch("/api/projects", { signal: controller.signal })
      .then(async response => { if (!response.ok) throw new Error("Project一覧を取得できませんでした"); return response.json(); })
      .then(data => {
        if (!data || !Array.isArray(data.projects) || !data.projects.every((p: unknown) => p && typeof p === "object" && "id" in p && typeof p.id === "string" && "name" in p && typeof p.name === "string")) throw new Error("Project APIの応答が不正です");
        if (!controller.signal.aborted) setProjects(data.projects as Project[]);
      })
      .catch(error => { if (!controller.signal.aborted) setProjectsError(error instanceof Error ? error.message : "取得エラー"); });
    return () => controller.abort();
  }, []);

  return <section className="panel" id="projects">
          <div className="panel-head"><span className="eyebrow">LOCAL PROJECTS</span><h2>Project・Repository</h2><p>複数Repositoryの管理用メタデータです。開発実行には登録不要です。実行対象とHarnessは実行設定から適用します。</p></div>
          <form className="project-form" onSubmit={event => { event.preventDefault(); void createProject(); }}>
            <label>新しいProject名<input aria-label="新しいProject名" maxLength={120} value={projectName} onChange={event => setProjectName(event.target.value)} placeholder="例: My Service" /></label>
            <button type="submit" disabled={projectBusy || !projectName.trim() || !connected}>{projectBusy ? "登録中..." : "Projectを登録"}</button>
          </form>
          {projectMessage && <p role="status">{projectMessage}</p>}
          {projectsError && <p role="alert">{projectsError}</p>}
          {connected && (projects.length ? <>
            <label className="project-selector">Projectを選択<select aria-label="Projectを選択" value={selectedProject} onChange={event => { setSelectedProject(event.target.value); setRepoMessage(""); }}><option value="">選択してください</option>{projects.map(project => <option key={project.id} value={project.id}>{project.name}</option>)}</select></label>
            {selectedProject && <>
              <form className="project-form project-register-form" onSubmit={event => { event.preventDefault(); void createRepository(); }}>
                <label>接続先<select aria-label="Repositoryの接続先" value={repoProvider} onChange={event => { setRepoProvider(event.target.value); setRepoVisibility(event.target.value === "local-git" ? "local" : "private"); }}><option value="github">GitHub（メタデータ登録のみ）</option><option value="local-git">ローカルGit</option></select></label>
                <label>{repoProvider === "local-git" ? "Repositoryのパス" : "Repository（owner/repo）"}<input aria-label="Repositoryの場所" maxLength={500} value={repoLocation} onChange={event => setRepoLocation(event.target.value)} placeholder={repoProvider === "local-git" ? "/path/to/repository" : "owner/repo"} /></label>
                <label>公開範囲<select aria-label="公開範囲" value={repoVisibility} onChange={event => setRepoVisibility(event.target.value)}><option value="local">local</option><option value="private">private</option><option value="public">public</option></select></label>
                <button type="submit" disabled={repoBusy || projectLoading || !repoLocation.trim() || !connected}>{repoBusy ? "登録中..." : "Repositoryを追加"}</button>
              </form>
              {repoMessage && <p role="status">{repoMessage}</p>}
              {projectError ? <p role="alert">{projectError}</p> : projectLoading ? <p role="status">Repositoryを読み込み中...</p> : projectRepos.length ? <div className="repository-list">{projectRepos.map(repo => <div className="repository-row" key={repo.id}><span><strong>{repo.external_id}</strong><small>{repo.provider_id} · {repo.visibility}</small></span></div>)}</div> : <p>Repositoryはまだ登録されていません。</p>}
            </>}
          </> : !projectsError && <p>Projectはまだ登録されていません。上のフォームから追加できます。</p>)}
        </section>;
}
