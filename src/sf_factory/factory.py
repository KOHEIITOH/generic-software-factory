"""Local persistent issue/run orchestration (read-only MVP)."""
from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from sf_factory.agent_registry import AgentRuntimeRegistry, default_runtime_registry
from sf_factory.evidence_state import EvidenceState
from sf_factory.harness_state import HarnessState
from sf_factory.issue_reference import IssueSnapshot
from sf_factory.policy import Capability, ExecutionPolicy, ExecutionRequest
from sf_factory.repository_contracts import ProjectRegistry, RepositoryBindingAdapter
from sf_factory.source_state import SourceState
from sf_factory.sqlite_state import SqliteIssueStore
from sf_factory.state_store import IssueStore, StateConflict


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
        if (self.root / 'issues-v2').exists():
            raise StateConflict('File state exists; use open_factory or a separate SQLite root')
        self.workspaces = self.root / "workspaces"
        self.workspaces.mkdir(exist_ok=True)
        self.db = self.root / "factory.sqlite3"
        self.issue_store: IssueStore = SqliteIssueStore(self.db)
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, issue_key TEXT NOT NULL REFERENCES issues(issue_key),
                    issue_snapshot TEXT NOT NULL,
                    runtime TEXT NOT NULL, status TEXT NOT NULL, workspace TEXT NOT NULL,
                    started_at TEXT NOT NULL, ended_at TEXT, output TEXT,
                    error_kind TEXT, error_message TEXT, exit_code INTEGER
                );
                CREATE TABLE IF NOT EXISTS run_harness_manifests (
                    run_id TEXT PRIMARY KEY REFERENCES runs(id),
                    approval_id TEXT NOT NULL UNIQUE REFERENCES harness_approvals(id),
                    manifest TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS issue_repositories (
                    issue_key TEXT PRIMARY KEY REFERENCES issues(issue_key),
                    repository TEXT NOT NULL, local_path TEXT NOT NULL, linked_at TEXT NOT NULL
                );
            """)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.db)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def import_issue(
        self, *, provider: str, instance: str, external_id: str,
        prompt: str, external_url: str | None = None,
    ) -> str:
        return self.issue_store.import_issue(
            provider=provider, instance=instance, external_id=external_id,
            prompt=prompt, external_url=external_url,
        )

    def _configure_repository_binding(self, adapter: RepositoryBindingAdapter | None) -> None:
        from sf_factory.integration_defaults import repository_binding

        self.repository_binding = adapter if adapter is not None else repository_binding()

    def _verified_binding(self, issue_key: str, repository: str, local_path: Path) -> Path:
        source = self.issue_repository(issue_key)
        if not source['provider'] or not source['instance']:
            raise ValueError('an external issue source is required')
        root = self.repository_binding.verify(
            provider=source['provider'], instance=source['instance'],
            repository=repository, local_path=local_path,
        )
        if not root.is_absolute() or not root.is_dir() or root != root.resolve(strict=True):
            raise ValueError('binding adapter must return a canonical repository root')
        return root

    def bind_issue_repository(
        self, issue_key: str, repository: str, local_path: Path
    ) -> dict[str, str]:
        """Persist an adapter-verified issue/repository binding; never execute code."""
        root = self._verified_binding(issue_key, repository, local_path)
        with self._connect() as db:
            db.execute(
                "INSERT INTO issue_repositories(issue_key,repository,local_path,linked_at) "
                "VALUES (?,?,?,?) ON CONFLICT(issue_key) DO UPDATE SET "
                "repository=excluded.repository,local_path=excluded.local_path,"
                "linked_at=excluded.linked_at",
                (issue_key, repository, str(root), _now()),
            )
            db.execute(
                "INSERT INTO audit(run_id,issue_key,event,at) VALUES (NULL,?,?,?)",
                (issue_key, "issue.repository_bound", _now()),
            )
        return {"issue_key": issue_key, "repository": repository, "local_path": str(root)}

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

    def issue_repository(self, issue_key: str) -> dict:
        issue = self.issue_store.get_issue(issue_key)
        with self._connect() as db:
            row = db.execute('SELECT repository,local_path FROM issue_repositories '
                             'WHERE issue_key=?',
                             (issue_key,)).fetchone()
        return {'key': issue_key, 'provider': issue.provider, 'instance': issue.instance,
                'repository': row['repository'] if row else None,
                'local_path': row['local_path'] if row else None}

    def list_issues(self, limit: int = 50) -> list[dict]:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError('bounded Issue limit required')
        with self._connect() as db:
            rows = db.execute('SELECT i.issue_key AS key,i.provider,i.instance,i.external_id,'
                'i.prompt,i.observed_at,i.external_url,r.repository AS bound_repository,'
                'r.local_path AS bound_local_path FROM issues i LEFT JOIN issue_repositories r '
                'ON r.issue_key=i.issue_key ORDER BY i.observed_at DESC,i.issue_key DESC LIMIT ?',
                (limit,)).fetchall()
        return [dict(row) for row in rows]

    def issue_history(self, limit: int = 50) -> list[dict]:
        """Group Runs by the externally derived Issue reference."""
        issues = self.list_issues(limit)
        history = self._issue_run_history(tuple(issue['key'] for issue in issues))
        return [{**issue, 'recent_runs': history.get(issue['key'], {}).get('runs', []),
                 'total_runs': history.get(issue['key'], {}).get('total', 0)} for issue in issues]

    def _issue_run_history(self, issue_keys: tuple[str, ...]) -> dict:
        if not issue_keys:
            return {}
        placeholders = ','.join('?' for _ in issue_keys)
        with self._connect() as db:
            rows = db.execute(
                'SELECT * FROM (SELECT id,issue_key,runtime,status,started_at,ended_at, '
                'ROW_NUMBER() OVER (PARTITION BY issue_key '
                'ORDER BY started_at DESC,id DESC) AS rank, '
                'COUNT(*) OVER (PARTITION BY issue_key) AS total FROM runs '
                f'WHERE issue_key IN ({placeholders})) WHERE rank <= 10 '
                'ORDER BY started_at DESC,id DESC', issue_keys,
            ).fetchall()
        history: dict = {}
        for row in rows:
            group = history.setdefault(row['issue_key'], {'runs': [], 'total': row['total']})
            group['runs'].append({k: row[k] for k in (
                'id', 'issue_key', 'runtime', 'status', 'started_at', 'ended_at')})
        return history

    def list_runs(self, limit: int = 50) -> list[dict]:
        if not 1 <= limit <= 100:
            raise ValueError('limit must be between 1 and 100')
        with self._connect() as db:
            rows = db.execute(
                'SELECT id,issue_key,runtime,status,started_at,ended_at FROM runs '
                'ORDER BY started_at DESC, id DESC LIMIT ?',
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def show_issue(self, issue_key: str) -> dict:
        issue = self.issue_store.get_issue(issue_key)
        with self._connect() as db:
            runs = db.execute(
                "SELECT id,runtime,status,started_at FROM runs "
                "WHERE issue_key=? ORDER BY started_at",
                (issue_key,),
            ).fetchall()
            return {"issue": issue.public(), "runs": [dict(row) for row in runs]}

    def show_run(self, run_id: str) -> dict:
        with self._connect() as db:
            row = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
            if row is None:
                raise ValueError("run not found")
            result = dict(row)
            result['issue_snapshot'] = json.loads(result['issue_snapshot'])
            if IssueSnapshot(**result['issue_snapshot']).key != result['issue_key']:
                raise StateConflict('Run Issue reference differs from snapshot')
            manifest = db.execute(
                "SELECT manifest FROM run_harness_manifests WHERE run_id=?", (run_id,),
            ).fetchone()
            if manifest is not None:
                result["harness_manifest"] = json.loads(manifest["manifest"])
            return result

    def run_issue(self, issue_key: str, runtime_name: str, timeout_seconds: int = 120) -> dict:
        if runtime_name not in self.runtime_registry.names():
            raise ValueError("unsupported runtime")
        policy_result = ExecutionPolicy().evaluate(
            ExecutionRequest(capability=Capability.READ_ONLY, timeout_seconds=timeout_seconds)
        )
        if not policy_result.allowed:
            raise ValueError(f"execution denied by policy: {policy_result.reason}")
        issue = self.issue_store.get_issue(issue_key)
        run_id = uuid.uuid4().hex
        workspace = self.workspaces / run_id
        workspace.mkdir(mode=0o700)
        self._start_run(run_id, issue_key, runtime_name, workspace, issue_snapshot=asdict(issue))
        try:
            runtime = self.runtime_registry.create(runtime_name)
            result = runtime.execute(prompt=issue.prompt, workspace=workspace,
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
        self._finish_run(run_id, issue_key, status, output, error_kind, error_message, exit_code)
        return self.show_run(run_id)

    def _start_run(self, run_id: str, issue_key: str, runtime: str, workspace: Path,
                   *, issue_snapshot: dict | None = None) -> None:
        snapshot = issue_snapshot or asdict(self.issue_store.get_issue(issue_key))
        if IssueSnapshot(**snapshot).key != issue_key:
            raise StateConflict('Run Issue reference differs from snapshot')
        with self._connect() as db:
            db.execute(
                "INSERT INTO runs(id,issue_key,issue_snapshot,runtime,status,workspace,started_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (run_id, issue_key, json.dumps(snapshot),
                 runtime, "running", str(workspace), _now()),
            )
            db.execute("INSERT INTO audit(run_id,issue_key,event,at) VALUES (?,?,?,?)",
                       (run_id, issue_key, "run.started", _now()))

    def _finish_run(self, run_id, issue_key, status, output, error_kind, error_message, exit_code):
        with self._connect() as db:
            updated = db.execute("""UPDATE runs SET status=?,ended_at=?,output=?,error_kind=?,
                       error_message=?,exit_code=? WHERE id=? AND issue_key=?
                       AND status='running'""",
                       (status, _now(), output, error_kind, error_message, exit_code,
                        run_id, issue_key))
            if updated.rowcount != 1:
                raise StateConflict('Run is not active or belongs to another issue')
            db.execute("INSERT INTO audit(run_id,issue_key,event,at) VALUES (?,?,?,?)",
                       (run_id, issue_key, "run." + status, _now()))
