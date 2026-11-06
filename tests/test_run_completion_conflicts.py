"""Late runtime results cannot resurrect terminal state or target another Task."""
import uuid

import pytest

from sf_factory.factory import Factory, _now
from sf_factory.file_dashboard import FileDashboardFactory
from sf_factory.runtime import RuntimeResult
from sf_factory.state_store import StateConflict


@pytest.fixture(params=['sqlite', 'file'])
def factory(request, tmp_path):
    return Factory(tmp_path) if request.param == 'sqlite' else FileDashboardFactory(tmp_path)


def test_late_completion_does_not_overwrite_terminal_run(factory, monkeypatch):
    task_id = factory.create_task('Read only')
    def execute(self, *, prompt, workspace, timeout_seconds):
        run_id = workspace.name
        if isinstance(factory, FileDashboardFactory):
            with factory._document(edit=True) as state:
                state['runs'][run_id].update(status='failed', ended_at=_now(),
                                            error_message='Stopped by trusted controller')
        else:
            with factory._connect() as db:
                db.execute("UPDATE runs SET status='failed',ended_at=?,error_message=? WHERE id=?",
                           (_now(), 'Stopped by trusted controller', run_id))
        return RuntimeResult('codex', 'succeeded', 'late output', 0)
    monkeypatch.setattr('sf_factory.codex_cli.CodexCliRuntime.execute', execute)
    with pytest.raises(StateConflict):
        factory.run_task(task_id, 'codex')
    run = factory.show_run(factory.list_runs()[0]['id'])
    assert run['status'] == 'failed'
    assert run['error_message'] == 'Stopped by trusted controller'
    assert run['output'] is None
    if isinstance(factory, FileDashboardFactory):
        with factory._document() as state:
            assert not any(e['event'] == 'run.succeeded' for e in state['events'])
    else:
        with factory._connect() as db:
            count = db.execute("SELECT COUNT(*) FROM audit WHERE event='run.succeeded'")
            assert count.fetchone()[0] == 0


def test_wrong_task_callback_does_not_modify_active_run(factory):
    task = factory.create_task('Correct Task')
    other = factory.create_task('Other Task')
    run_id = uuid.uuid4().hex
    workspace = factory.workspaces / run_id
    workspace.mkdir()
    factory._start_run(run_id, task, 'codex', workspace)
    before = factory.show_run(run_id)
    with pytest.raises(StateConflict):
        factory._finish_run(run_id, other, 'succeeded', 'wrong callback', None, None, 0)
    assert factory.show_run(run_id) == before
    factory._finish_run(run_id, task, 'succeeded', 'correct callback', None, None, 0)
    assert factory.show_run(run_id)['output'] == 'correct callback'


def test_completion_of_unknown_run_never_creates_history(factory):
    task = factory.create_task('Known Task')
    with pytest.raises(StateConflict):
        factory._finish_run(uuid.uuid4().hex, task, 'succeeded', 'unknown', None, None, 0)
    assert factory.list_runs() == []
