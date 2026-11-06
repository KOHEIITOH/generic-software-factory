"""Local persistent task/run orchestration (read-only MVP)."""
from __future__ import annotations

import sqlite3
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from sf_factory.agent_registry import AgentRuntimeRegistry, default_runtime_registry
from sf_factory.evidence_state import EvidenceState
from sf_factory.harness_state import HarnessState
from sf_factory.policy import Capability, ExecutionPolicy, ExecutionRequest
from sf_factory.repository_contracts import ProjectRegistry, RepositoryBindingAdapter
from sf_factory.source_state import SourceState
from sf_factory.sqlite_state import SqliteStateStore
from sf_factory.state_store import StateConflict, StateStore


def _now() -> str:
    return datetime.now(UTC).isoformat()

class Factory:
    def __init__(self, root: Path, *, runtime_registry: AgentRuntimeRegistry | None = None,
                 repository_binding: RepositoryBindingAdapter | None = None):
        self.runtime_registry = (
            runtime_registry if runtime_registry is not None else default_runtime_registry()
        )
        self._configure_repository_binding(repository_binding)
        self.root = root.expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        if (self.root / 'tasks-v1').exists():
            raise StateConflict('File state exists; use open_factory or a separate SQLite root')
        self.workspaces = self.root / "workspaces"
        self.workspaces.mkdir(exist_ok=True)
        self.db = self.root / "factory.sqlite3"
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY, prompt TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id),
                    runtime TEXT NOT NULL, status TEXT NOT NULL, workspace TEXT NOT NULL,
                    started_at TEXT NOT NULL, ended_at TEXT, output TEXT,
                    error_kind TEXT, error_message TEXT, exit_code INTEGER
                );
                CREATE TABLE IF NOT EXISTS audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT,
                    task_id TEXT NOT NULL, event TEXT NOT NULL, at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS run_harness_manifests (
                    run_id TEXT PRIMARY KEY REFERENCES runs(id),
                    approval_id TEXT NOT NULL UNIQUE REFERENCES harness_approvals(id),
                    manifest TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS task_repositories (
                    task_id TEXT PRIMARY KEY REFERENCES tasks(id),
                    repository TEXT NOT NULL, local_path TEXT NOT NULL,
                    linked_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS task_sources (
                    task_id TEXT PRIMARY KEY REFERENCES tasks(id),
                    provider TEXT NOT NULL, instance TEXT NOT NULL,
                    external_id TEXT NOT NULL, external_url TEXT,
                    UNIQUE(provider, instance, external_id)
                );
            """)

        self.task_store: StateStore = SqliteStateStore(self.db)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.db)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def create_task(self, prompt: str) -> str:
        return self.task_store.create_task(prompt)

    def import_external_task(
        self, *, provider: str, instance: str, external_id: str,
        prompt: str, external_url: str | None = None,
    ) -> str:
        return self.task_store.import_external_task(
            provider=provider, instance=instance, external_id=external_id,
            prompt=prompt, external_url=external_url,
        )

    def _configure_repository_binding(self, adapter: RepositoryBindingAdapter | None) -> None:
        from sf_factory.integration_defaults import repository_binding

        self.repository_binding = adapter if adapter is not None else repository_binding()

    def _verified_binding(self, task_id: str, repository: str, local_path: Path) -> Path:
        source = self.task_repository(task_id)
        if not source['provider'] or not source['instance']:
            raise ValueError('an external task source is required')
        root = self.repository_binding.verify(
            provider=source['provider'], instance=source['instance'],
            repository=repository, local_path=local_path,
        )
        if not root.is_absolute() or not root.is_dir() or root != root.resolve(strict=True):
            raise ValueError('binding adapter must return a canonical repository root')
        return root

    def bind_task_repository(
        self, task_id: str, repository: str, local_path: Path
    ) -> dict[str, str]:
        """Persist an adapter-verified task/repository binding; never execute code."""
        root = self._verified_binding(task_id, repository, local_path)
        with self._connect() as db:
            db.execute(
                "INSERT INTO task_repositories(task_id,repository,local_path,linked_at) "
                "VALUES (?,?,?,?) ON CONFLICT(task_id) DO UPDATE SET "
                "repository=excluded.repository,local_path=excluded.local_path,"
                "linked_at=excluded.linked_at",
                (task_id, repository, str(root), _now()),
            )
            db.execute(
                "INSERT INTO audit(run_id,task_id,event,at) VALUES (NULL,?,?,?)",
                (task_id, "task.repository_bound", _now()),
            )
        return {"task_id": task_id, "repository": repository, "local_path": str(root)}

    def evidence_state(self) -> EvidenceState:
        from sf_factory.sqlite_evidence_state import SqliteEvidenceState

        return SqliteEvidenceState(self)

    def source_state(self) -> SourceState:
        from sf_factory.source_state import SqliteSourceState

        return SqliteSourceState(self)

    def harness_state(self) -> HarnessState:
        from sf_factory.sqlite_harness_state import SqliteHarnessState

        return SqliteHarnessState(self)

    def project_registry(self) -> ProjectRegistry:
        from sf_factory.local_project_registry import LocalProjectRegistry

        return LocalProjectRegistry(self.db)

    def task_repository(self, task_id: str) -> dict:
        """Return source/binding metadata without exposing the storage connection."""
        with self._connect() as db:
            row = db.execute(
                "SELECT t.id,s.provider,s.instance,tr.repository,tr.local_path "
                "FROM tasks t LEFT JOIN task_sources s ON s.task_id=t.id "
                "LEFT JOIN task_repositories tr ON tr.task_id=t.id WHERE t.id=?",
                (task_id,),
            ).fetchone()
        if row is None:
            raise ValueError('task not found')
        return dict(row)

    def list_tasks(self, limit: int = 50, *, external_only: bool = False) -> list[dict]:
        if not 1 <= limit <= 100:
            raise ValueError('limit must be between 1 and 100')
        with self._connect() as db:
            rows = db.execute(
                'SELECT t.id,t.prompt,t.created_at,s.provider,s.instance, '
                's.external_id,s.external_url,tr.repository AS bound_repository, '
                'tr.local_path AS bound_local_path '
                'FROM tasks t LEFT JOIN task_sources s ON s.task_id=t.id '
                'LEFT JOIN task_repositories tr ON tr.task_id=t.id '
                + ('WHERE s.task_id IS NOT NULL ' if external_only else '')
                + 'ORDER BY t.created_at DESC, t.id DESC LIMIT ?',
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def issue_history(self, limit: int = 50) -> list[dict]:
        """Issue is the request; keep the legacy Task ID as an internal reference."""
        issues = self.list_tasks(limit, external_only=True)
        history = self._issue_run_history(tuple(issue['id'] for issue in issues))
        return [{**issue, 'recent_runs': history.get(issue['id'], {}).get('runs', []),
                 'total_runs': history.get(issue['id'], {}).get('total', 0)} for issue in issues]

    def _issue_run_history(self, task_ids: tuple[str, ...]) -> dict:
        if not task_ids:
            return {}
        placeholders = ','.join('?' for _ in task_ids)
        with self._connect() as db:
            rows = db.execute(
                'SELECT * FROM (SELECT id,task_id,runtime,status,started_at,ended_at, '
                'ROW_NUMBER() OVER (PARTITION BY task_id '
                'ORDER BY started_at DESC,id DESC) AS rank, '
                'COUNT(*) OVER (PARTITION BY task_id) AS total FROM runs '
                f'WHERE task_id IN ({placeholders})) WHERE rank <= 10 '
                'ORDER BY started_at DESC,id DESC', task_ids,
            ).fetchall()
        history: dict = {}
        for row in rows:
            group = history.setdefault(row['task_id'], {'runs': [], 'total': row['total']})
            group['runs'].append({k: row[k] for k in (
                'id', 'task_id', 'runtime', 'status', 'started_at', 'ended_at')})
        return history

    def list_runs(self, limit: int = 50) -> list[dict]:
        if not 1 <= limit <= 100:
            raise ValueError('limit must be between 1 and 100')
        with self._connect() as db:
            rows = db.execute(
                'SELECT id,task_id,runtime,status,started_at,ended_at FROM runs '
                'ORDER BY started_at DESC, id DESC LIMIT ?',
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def show_task(self, task_id: str) -> dict:
        task = self.task_store.get_task(task_id)
        with self._connect() as db:
            runs = db.execute(
                "SELECT id,runtime,status,started_at FROM runs WHERE task_id=? ORDER BY started_at",
                (task_id,),
            ).fetchall()
            return {"task": asdict(task), "runs": [dict(row) for row in runs]}

    def show_run(self, run_id: str) -> dict:
        with self._connect() as db:
            row = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
            if row is None:
                raise ValueError("run not found")
            result = dict(row)
            manifest = db.execute(
                "SELECT manifest FROM run_harness_manifests WHERE run_id=?", (run_id,),
            ).fetchone()
            if manifest is not None:
                import json

                result["harness_manifest"] = json.loads(manifest["manifest"])
            return result

    def run_task(self, task_id: str, runtime_name: str, timeout_seconds: int = 120) -> dict:
        if runtime_name not in self.runtime_registry.names():
            raise ValueError("unsupported runtime")
        policy_result = ExecutionPolicy().evaluate(
            ExecutionRequest(capability=Capability.READ_ONLY, timeout_seconds=timeout_seconds)
        )
        if not policy_result.allowed:
            raise ValueError(f"execution denied by policy: {policy_result.reason}")
        task = self.task_store.get_task(task_id)
        run_id = uuid.uuid4().hex
        workspace = self.workspaces / run_id
        workspace.mkdir(mode=0o700)
        self._start_run(run_id, task_id, runtime_name, workspace)
        try:
            runtime = self.runtime_registry.create(runtime_name)
            result = runtime.execute(prompt=task.prompt, workspace=workspace,
                                     timeout_seconds=timeout_seconds)
            status = result.status
            output = result.output
            error_kind = result.error_kind
            error_message = result.error_message
            exit_code = result.exit_code
        except Exception as exc:
            status, output, error_kind, error_message, exit_code = (
                "failed", "", "runtime_error", str(exc), None
            )
        self._finish_run(run_id, task_id, status, output, error_kind, error_message, exit_code)
        return self.show_run(run_id)

    def _start_run(self, run_id: str, task_id: str, runtime: str, workspace: Path) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT INTO runs(id,task_id,runtime,status,workspace,started_at) "
                "VALUES (?,?,?,?,?,?)",
                (run_id, task_id, runtime, "running", str(workspace), _now()),
            )
            db.execute("INSERT INTO audit(run_id,task_id,event,at) VALUES (?,?,?,?)",
                       (run_id, task_id, "run.started", _now()))

    def _finish_run(self, run_id, task_id, status, output, error_kind, error_message, exit_code):
        with self._connect() as db:
            updated = db.execute("""UPDATE runs SET status=?,ended_at=?,output=?,error_kind=?,
                       error_message=?,exit_code=? WHERE id=? AND task_id=? AND status='running'""",
                       (status, _now(), output, error_kind, error_message, exit_code,
                        run_id, task_id))
            if updated.rowcount != 1:
                raise StateConflict('Run is not active or belongs to another task')
            db.execute("INSERT INTO audit(run_id,task_id,event,at) VALUES (?,?,?,?)",
                       (run_id, task_id, "run." + status, _now()))
