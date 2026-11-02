"""Local persistent task/run orchestration (read-only MVP)."""
from __future__ import annotations

import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sf_factory.agent_registry import AgentRuntimeRegistry, default_runtime_registry
from sf_factory.policy import Capability, ExecutionPolicy, ExecutionRequest


def _now() -> str:
    return datetime.now(UTC).isoformat()

class Factory:
    def __init__(self, root: Path, *, runtime_registry: AgentRuntimeRegistry | None = None):
        self.runtime_registry = runtime_registry if runtime_registry is not None else default_runtime_registry()
        self.root = root.expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
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
            """)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.db)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def create_task(self, prompt: str) -> str:
        if not prompt.strip():
            raise ValueError("task prompt must not be empty")
        task_id = uuid.uuid4().hex
        with self._connect() as db:
            db.execute("INSERT INTO tasks VALUES (?,?,?)", (task_id, prompt, _now()))
            db.execute("INSERT INTO audit(run_id,task_id,event,at) VALUES (NULL,?,?,?)",
                       (task_id, "task.created", _now()))
        return task_id

    def show_task(self, task_id: str) -> dict:
        with self._connect() as db:
            task = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            if task is None:
                raise ValueError("task not found")
            runs = db.execute(
                "SELECT id,runtime,status,started_at FROM runs WHERE task_id=? ORDER BY started_at",
                (task_id,),
            ).fetchall()
            return {"task": dict(task), "runs": [dict(row) for row in runs]}

    def show_run(self, run_id: str) -> dict:
        with self._connect() as db:
            row = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
            if row is None:
                raise ValueError("run not found")
            return dict(row)

    def run_task(self, task_id: str, runtime_name: str, timeout_seconds: int = 120) -> dict:
        if runtime_name not in self.runtime_registry.names():
            raise ValueError("unsupported runtime")
        policy_result = ExecutionPolicy().evaluate(
            ExecutionRequest(capability=Capability.READ_ONLY, timeout_seconds=timeout_seconds)
        )
        if not policy_result.allowed:
            raise ValueError(f"execution denied by policy: {policy_result.reason}")
        with self._connect() as db:
            task = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if task is None:
            raise ValueError("task not found")
        run_id = uuid.uuid4().hex
        workspace = self.workspaces / run_id
        workspace.mkdir(mode=0o700)
        with self._connect() as db:
            db.execute(
                "INSERT INTO runs(id,task_id,runtime,status,workspace,started_at) "
                "VALUES (?,?,?,?,?,?)",
                       (run_id, task_id, runtime_name, "running", str(workspace), _now()))
            db.execute("INSERT INTO audit(run_id,task_id,event,at) VALUES (?,?,?,?)",
                       (run_id, task_id, "run.started", _now()))
        try:
            runtime = self.runtime_registry.create(runtime_name)
            result = runtime.execute(prompt=task["prompt"], workspace=workspace,
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
        with self._connect() as db:
            db.execute("""UPDATE runs SET status=?,ended_at=?,output=?,error_kind=?,
                       error_message=?,exit_code=? WHERE id=?""",
                       (status, _now(), output, error_kind, error_message, exit_code, run_id))
            db.execute("INSERT INTO audit(run_id,task_id,event,at) VALUES (?,?,?,?)",
                       (run_id, task_id, "run." + status, _now()))
        return self.show_run(run_id)
