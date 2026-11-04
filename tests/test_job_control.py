import json
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.memory.context import bounded_context
from app.memory.jobs import JobStore
from app.models.jobs import JobRequest
from app.orchestrator.control import BudgetExceeded, JobControl, RunControl, RunStopped
from app.orchestrator.jobs import SchedulerLock
from app.utils.logging import RunLogger
from app.utils.patches import PreviewChange


def wait_for(predicate, seconds=8):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        value = predicate()
        if value:
            return value
        time.sleep(.03)
    raise AssertionError("Expected state was not reached")


def owned_job(tmp_path):
    store = JobStore(tmp_path)
    job = store.submit(JobRequest(task="Test"))
    store.heartbeat("owner")
    store.claim("owner")
    logger = RunLogger(tmp_path)
    logger.start("implement", "Test", "demo")
    store.attach(job["id"], "owner", logger.run_id)
    return store, job["id"], logger


def test_claim_is_atomic_and_queue_survives_reopen(tmp_path):
    store = JobStore(tmp_path)
    job = store.submit(JobRequest(task="Test"))
    with ThreadPoolExecutor(max_workers=4) as pool:
        claims = list(pool.map(lambda owner: store.claim(owner), ["a", "b", "c", "d"]))
    assert sum(claim is not None for claim in claims) == 1
    assert JobStore(tmp_path).get(job["id"])["state"] == "running"


def test_recovery_marks_active_jobs_interrupted_and_keeps_queued(tmp_path):
    store, job_id, _ = owned_job(tmp_path)
    queued = store.submit(JobRequest(task="Later"))
    assert [job["id"] for job in store.recover()] == [job_id]
    assert store.get(job_id)["state"] == "interrupted"
    assert store.get(queued["id"])["state"] == "queued"
    retried = store.retry(job_id)
    assert retried["id"] != job_id
    assert retried["retry_of"] == job_id


def test_stale_approval_and_replay_are_rejected(tmp_path):
    store, job_id, logger = owned_job(tmp_path)
    control = JobControl(store, job_id, "owner", logger, 5, 1000)
    with ThreadPoolExecutor() as pool:
        approval = pool.submit(control.approve, [PreviewChange(tmp_path / "a.py", "create_or_update", "specific diff", False)])
        row = wait_for(lambda: store.get(job_id) if store.get(job_id)["approval"] else None)
        ticket = row["approval"]["ticket"]
        with pytest.raises(ValueError, match="stale"):
            store.decide(job_id, "old-ticket", True)
        assert not approval.done()
        store.decide(job_id, ticket, True)
        assert approval.result(timeout=3)
        with pytest.raises(ValueError, match="No pending"):
            store.decide(job_id, ticket, True)


def test_cancel_while_waiting_for_approval_never_approves(tmp_path):
    store, job_id, logger = owned_job(tmp_path)
    control = JobControl(store, job_id, "owner", logger, 5, 1000)
    with ThreadPoolExecutor() as pool:
        approval = pool.submit(control.approve, [PreviewChange(tmp_path / "a.py", "delete", "remove file", True)])
        wait_for(lambda: store.get(job_id)["approval"])
        store.cancel(job_id)
        with pytest.raises(RunStopped):
            approval.result(timeout=3)


def test_decline_stops_the_run(tmp_path):
    store, job_id, logger = owned_job(tmp_path)
    control = JobControl(store, job_id, "owner", logger, 5, 1000)
    with ThreadPoolExecutor() as pool:
        approval = pool.submit(control.approve, [PreviewChange(tmp_path / "a.py", "delete", "remove file", True)])
        row = wait_for(lambda: store.get(job_id)["approval"])
        store.decide(job_id, row["ticket"], False)
        with pytest.raises(RunStopped, match="declined"):
            approval.result(timeout=3)


def test_call_budget_is_shared_across_parallel_agents():
    control = RunControl(max_calls=3)
    def call(_):
        try:
            control.before_call()
            return True
        except BudgetExceeded:
            return False
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(call, range(20))) == 3


def test_reported_token_limit_blocks_subsequent_requests():
    control = RunControl(max_tokens=100)
    control.before_call()
    control.record_tokens(100)
    with pytest.raises(BudgetExceeded, match="token"):
        control.before_call()


def test_context_budget_preserves_valid_unicode_json_and_marks_omission():
    context = {"focused_files": {str(n): "🙂" * 20000 for n in range(8)}, "mode": "implement"}
    bounded, truncated = bounded_context(context, 4000)
    assert truncated
    assert len(json.dumps(bounded, ensure_ascii=False).encode("utf-8")) <= 4000
    assert bounded["_context_notice"]
    assert context["focused_files"]["0"] == "🙂" * 20000


def test_only_one_scheduler_owns_a_data_directory(tmp_path):
    first, second = SchedulerLock(tmp_path / "lock"), SchedulerLock(tmp_path / "lock")
    first.acquire()
    try:
        with pytest.raises(RuntimeError, match="Another dashboard"):
            second.acquire()
    finally:
        first.release()
    second.acquire()
    second.release()


def test_queued_cancel_is_terminal_and_not_claimed(tmp_path):
    store = JobStore(tmp_path)
    job = store.submit(JobRequest(task="Task"))
    assert store.cancel(job["id"])["state"] == "cancelled"
    assert store.claim("owner") is None


def test_active_job_cannot_be_retried(tmp_path):
    store = JobStore(tmp_path)
    job = store.submit(JobRequest(task="Task"))
    with pytest.raises(ValueError):
        store.retry(job["id"])


def test_managed_application_waits_for_approval_and_rejects_changed_baseline(tmp_path, monkeypatch):
    from app.models.settings import Settings
    from app.orchestrator.engine import Orchestrator
    engine = Orchestrator(tmp_path, Settings(_env_file=None, nvidia_provider_mode="demo", swarm_auto_apply=True))
    original = engine.provider_registry.demo._render
    def render(agent, task):
        if agent == "coder":
            return json.dumps({"changes": [{"path": "example.py", "content": "value = 2"}]})
        return original(agent, task)
    engine.provider_registry.demo._render = render
    def approve(previews):
        (tmp_path / "example.py").write_text("user_edit = True")
        return True
    engine.run_logger.control.approve = approve
    with pytest.raises(ValueError, match="Files changed while awaiting approval"):
        engine.implement("Task", apply_changes=True)
    assert (tmp_path / "example.py").read_text() == "user_edit = True"


def test_supervisor_enforces_wall_clock_and_records_interruption(tmp_path):
    import subprocess, sys
    from app.orchestrator.jobs import JobManager
    from app.models.settings import Settings
    from app.memory.runs import RunStore
    manager = JobManager(tmp_path, Settings(_env_file=None))
    job = manager.submit(JobRequest(task="Task"))
    manager.store.heartbeat(manager.owner)
    manager.store.claim(manager.owner)
    logger = RunLogger(manager.data_dir)
    logger.start("plan", "Task", "demo")
    manager.store.attach(job["id"], manager.owner, logger.run_id)
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    handle = (tmp_path / "test.log").open("wb")
    manager.active[job["id"]] = (process, time.monotonic() - 20, 10, handle)
    try:
        manager._tick()
        assert process.poll() is not None
        assert manager.store.get(job["id"])["state"] == "budget_exceeded"
        assert RunStore(manager.data_dir).summary(logger.run_id)["status"] == "budget_exceeded"
    finally:
        if process.poll() is None:
            process.kill()
        handle.close()


def test_cancel_all_prevents_queued_jobs_from_starting(tmp_path):
    store, running, _ = owned_job(tmp_path)
    queued = store.submit(JobRequest(task="Later"))
    assert store.cancel_all() == 2
    assert store.get(running)["state"] == "cancelling"
    assert store.get(queued["id"])["state"] == "cancelled"
    assert store.claim("owner") is None


def test_durable_queue_is_bound_to_its_workspace(tmp_path):
    from app.orchestrator.jobs import JobManager
    from app.models.settings import Settings
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    settings = Settings(_env_file=None, swarm_data_dir=tmp_path / "shared")
    manager = JobManager(first, settings)
    manager.submit(JobRequest(task="First project task"))
    with pytest.raises(ValueError, match="another workspace"):
        JobManager(second, settings)
    assert len(manager.store.list()) == 1


def test_isolated_workspace_keeps_source_context_when_data_directory_is_its_ancestor(tmp_path):
    from app.orchestrator.engine import Orchestrator
    from app.models.settings import Settings
    data_dir = tmp_path / "data"
    worktree = data_dir / "workspaces" / "run"
    worktree.mkdir(parents=True)
    (worktree / "example.py").write_text("value = 1")
    engine = Orchestrator(worktree, Settings(_env_file=None, nvidia_provider_mode="demo", swarm_data_dir=data_dir))
    assert engine.repo.focused_snapshot("example") == {"example.py": "value = 1"}


def test_cli_submission_cancel_and_retry_use_durable_queue_and_operator_caps(tmp_path, monkeypatch):
    from typer.testing import CliRunner
    from app.cli.app import app
    from app.models.settings import Settings
    settings = Settings(_env_file=None, swarm_data_dir=tmp_path / "data", swarm_job_max_calls=4)
    monkeypatch.setattr("app.cli.app.get_settings", lambda: settings)
    runner = CliRunner()
    submitted = runner.invoke(app, ["submit", "Plan coverage", "--root", str(tmp_path)])
    assert submitted.exit_code == 0, submitted.output
    job = json.loads(submitted.stdout)
    assert job["request"]["max_model_calls"] == 4
    cancelled = runner.invoke(app, ["jobs", job["id"], "--root", str(tmp_path), "--cancel"])
    assert cancelled.exit_code == 0, cancelled.output
    assert json.loads(cancelled.stdout)["state"] == "cancelled"
    retried = runner.invoke(app, ["jobs", job["id"], "--root", str(tmp_path), "--retry"])
    assert retried.exit_code == 0, retried.output
    assert json.loads(retried.stdout)["retry_of"] == job["id"]
