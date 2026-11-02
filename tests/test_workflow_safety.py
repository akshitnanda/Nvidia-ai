import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from app.cli.app import app, emit_result
from app.models.runtime import ChangeSet, CommandExecution, ProposedFileChange
from app.models.settings import Settings
from app.orchestrator.engine import Orchestrator


def orchestrator(tmp_path: Path) -> Orchestrator:
    return Orchestrator(tmp_path, Settings(_env_file=None, nvidia_provider_mode="demo", swarm_auto_apply=True,
                                        swarm_default_test_command="trusted-test", swarm_default_lint_command="trusted-lint"))


def propose(engine: Orchestrator) -> None:
    original = engine.provider_registry.demo._render

    def render(agent: str, task: str) -> str:
        if agent == "coder":
            return json.dumps({"changes": [{"path": "example.py", "content": "value = 1\n"}],
                               "commands": ["untrusted-model-command"]})
        return original(agent, task)

    engine.provider_registry.demo._render = render


def test_preview_never_executes_commands_or_writes_proposal(tmp_path: Path) -> None:
    engine = orchestrator(tmp_path)
    propose(engine)
    engine.shell.run = Mock(side_effect=AssertionError("Preview ran a shell command"))
    result = engine.implement("Add a value")
    assert result.success
    assert result.validation_status == "not_run"
    assert "untrusted-model-command" in result.suggested_commands
    assert not (tmp_path / "example.py").exists()
    engine.shell.run.assert_not_called()
    manifest = json.loads((engine.run_logger.run_dir / "run.json").read_text())
    assert manifest["status"] == "succeeded"
    assert (engine.run_logger.run_dir / "events.jsonl").exists()


def test_failed_validation_reports_failure_and_skips_commit(tmp_path: Path) -> None:
    engine = orchestrator(tmp_path)
    propose(engine)
    engine.shell.run = Mock(side_effect=lambda command: CommandExecution(command=command, exit_code=1))
    engine.git.commit = Mock()
    result = engine.implement("Add a value", apply_changes=True, commit_message="test")
    assert not result.success
    assert result.validation_status == "failed"
    assert [call.args[0] for call in engine.shell.run.call_args_list] == ["trusted-test", "trusted-lint"]
    assert (tmp_path / "example.py").read_text() == "value = 1\n"
    engine.git.commit.assert_not_called()
    assert json.loads((engine.run_logger.run_dir / "run.json").read_text())["status"] == "failed"
    import typer
    with pytest.raises(typer.Exit) as exc:
        emit_result(True, result)
    assert exc.value.exit_code == 1


def test_declined_apply_does_not_validate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    engine = orchestrator(tmp_path)
    propose(engine)
    engine.settings.swarm_auto_apply = False
    monkeypatch.setattr("builtins.input", lambda _: "n")
    engine.shell.run = Mock()
    result = engine.implement("Add a value", apply_changes=True)
    assert result.changed_files == []
    engine.shell.run.assert_not_called()


def test_exception_is_persisted_with_partial_agent_artifacts(tmp_path: Path) -> None:
    engine = orchestrator(tmp_path)
    engine.provider_registry.demo.complete = Mock(side_effect=RuntimeError("offline"))
    with pytest.raises(RuntimeError, match="offline"):
        engine.plan("Fail")
    manifest = json.loads((engine.run_logger.run_dir / "run.json").read_text())
    assert manifest["status"] == "failed"
    assert manifest["error"] == "offline"
    events = [json.loads(line) for line in (engine.run_logger.run_dir / "events.jsonl").read_text().splitlines()]
    assert [event["status"] for event in events] == ["running", "failed"]


@pytest.mark.parametrize("paths", [["a.txt", "./a.txt"], ["folder", "folder/a.txt"]])
def test_conflicting_proposals_rejected_before_any_write(tmp_path: Path, paths: list[str]) -> None:
    engine = orchestrator(tmp_path)
    changeset = ChangeSet(changes=[ProposedFileChange(path=path, content="content") for path in paths])
    with pytest.raises(ValueError, match="Conflicting"):
        engine._apply_changes(changeset)
    assert not (tmp_path / paths[0]).exists()


def test_all_proposals_preflight_before_write(tmp_path: Path) -> None:
    engine = orchestrator(tmp_path)
    changes = [ProposedFileChange(path="fine.txt", content="ok"), ProposedFileChange(path=".env", content="no")]
    with pytest.raises(PermissionError):
        engine._apply_changes(ChangeSet(changes=changes))
    assert not (tmp_path / "fine.txt").exists()


def test_demo_and_history_json_roundtrip(tmp_path: Path) -> None:
    runner = CliRunner()
    run = runner.invoke(app, ["demo", "--mode", "implement", "--root", str(tmp_path), "--json"])
    assert run.exit_code == 0, run.output
    result = json.loads(run.stdout)
    history = runner.invoke(app, ["runs", result["run_id"], "--root", str(tmp_path), "--json"])
    assert history.exit_code == 0, history.output
    payload = json.loads(history.stdout)
    assert payload["summary"]["provider"] == "demo"
    assert payload["summary"]["model_calls"] == 6
    assert payload["artifacts"]["result.json"]["validation_status"] == "not_run"


def test_reused_orchestrator_keeps_distinct_runs(tmp_path: Path) -> None:
    engine = orchestrator(tmp_path)
    first = engine.plan("first")
    second = engine.plan("second")
    assert first.run_id != second.run_id
    for result in [first, second]:
        assert (tmp_path / "data" / "runs" / result.run_id / "result.json").exists()


def test_no_validation_means_no_automatic_commit(tmp_path: Path) -> None:
    engine = orchestrator(tmp_path)
    propose(engine)
    engine.git.commit = Mock()
    result = engine.implement("Add value", apply_changes=True, run_validation=False, commit_message="test")
    engine.git.commit.assert_not_called()
    assert "did not run" in result.outputs["commit"]


def test_watch_filters_artifact_and_secret_changes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.cli.app import watch_repo
    from watchfiles import Change
    monkeypatch.setattr("app.cli.app.get_settings", lambda: Settings(_env_file=None, swarm_data_dir=Path("custom")))

    def fake_watch(root, watch_filter):
        assert not watch_filter(Change.modified, str(tmp_path / "custom" / "runs" / "run.json"))
        assert not watch_filter(Change.modified, str(tmp_path / ".env.production"))
        assert not watch_filter(Change.modified, str(tmp_path / "example.py.backup.bak"))
        assert watch_filter(Change.modified, str(tmp_path / "example.py"))
        return []

    monkeypatch.setattr("app.cli.app.watch", fake_watch)
    from app.models.runtime import WorkflowMode
    watch_repo(task="test", mode=WorkflowMode.REVIEW, root=tmp_path)
