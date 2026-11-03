import json
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

from app.models.runtime import CommandExecution
from app.models.settings import Settings
from app.orchestrator.engine import Orchestrator


def engine(root: Path) -> Orchestrator:
    return Orchestrator(root, Settings(_env_file=None, nvidia_provider_mode="demo", swarm_auto_apply=True,
                                       swarm_default_test_command="trusted-test", swarm_default_lint_command=""))


def report(verdict="approve", severity=None):
    return json.dumps({"verdict": verdict, "summary": "Review evidence", "residual_risks": [],
                       "findings": [{"severity": severity, "title": "Issue", "detail": "Fix it"}] if severity else []})


def scripted(engine, reviews, repairs=None):
    original = engine.provider_registry.demo._render
    review_outputs = iter(reviews)
    proposals = iter(repairs or ["value = 1\n"])

    def render(agent, task):
        if agent == "coder":
            content = next(proposals)
            return json.dumps({"changes": [] if content is None else [{"path": "example.py", "content": content}]})
        if agent == "reviewer":
            return next(review_outputs)
        return original(agent, task)

    engine.provider_registry.demo._render = render


@pytest.mark.parametrize("output,status", [(report("request_changes"), "changes_requested"),
                                         (report(severity="high"), "changes_requested"),
                                         ("Looks good!", "invalid"), ('{"verdict":"approve"}', "invalid")])
def test_review_gate_blocks_commit(tmp_path, output, status):
    run = engine(tmp_path)
    scripted(run, [output])
    run.shell.run = Mock(return_value=CommandExecution(command="trusted-test", exit_code=0))
    run.git.commit = Mock()
    result = run.implement("Add value", apply_changes=True, commit_message="Change")
    assert not result.success
    assert result.review_status == status
    run.git.commit.assert_not_called()


def test_failed_validation_repair_revalidates_and_commits_only_final_files(tmp_path):
    run = engine(tmp_path)
    scripted(run, [report(), report()], ["value = broken\n", "value = 2\n"])
    run.shell.run = Mock(side_effect=[CommandExecution(command="trusted-test", exit_code=1, stderr="NameError"),
                                     CommandExecution(command="trusted-test", exit_code=0)])
    run.git.commit = Mock(return_value="committed")
    result = run.implement("Add value", apply_changes=True, max_repairs=1, commit_message="Fix")
    assert result.success
    assert [attempt.validation_status for attempt in result.attempts] == ["failed", "passed"]
    assert (tmp_path / "example.py").read_text() == "value = 2\n"
    run.git.commit.assert_called_once_with("Fix", ["example.py"])
    assert (run.run_logger.run_dir / "attempt-1-review.md").exists()
    assert (run.run_logger.run_dir / "attempt-2-changeset.json").exists()


def test_review_findings_feed_repair_and_budget_is_bounded(tmp_path):
    run = engine(tmp_path)
    scripted(run, [report("request_changes"), report("request_changes")], ["value = 1", "value = 2"])
    run.shell.run = Mock(return_value=CommandExecution(command="trusted-test", exit_code=0))
    result = run.implement("Add value", apply_changes=True, max_repairs=1)
    assert not result.success
    assert len(result.attempts) == 2


def test_noop_repair_preserves_failed_validation(tmp_path):
    run = engine(tmp_path)
    scripted(run, [report(), report()], ["value = broken", None])
    run.shell.run = Mock(return_value=CommandExecution(command="trusted-test", exit_code=1))
    result = run.implement("Add value", apply_changes=True, max_repairs=1)
    assert not result.success
    assert result.validation_status == "failed"
    assert run.shell.run.call_count == 1


def test_repair_requires_fresh_approval(tmp_path, monkeypatch):
    run = engine(tmp_path)
    run.settings.swarm_auto_apply = False
    scripted(run, [report(), report()], ["value = 1", "value = 2"])
    answers = iter(["y", "n"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    run.shell.run = Mock(return_value=CommandExecution(command="trusted-test", exit_code=1))
    result = run.implement("Add value", apply_changes=True, max_repairs=1)
    assert not result.success
    assert result.application_status == "declined"
    assert (tmp_path / "example.py").read_text() == "value = 1"
    assert run.shell.run.call_count == 1


@pytest.mark.parametrize("kwargs", [{"max_repairs": 4}, {"max_repairs": -1}, {"max_repairs": 1}])
def test_invalid_repair_options_make_no_provider_calls(tmp_path, kwargs):
    run = engine(tmp_path)
    run.provider_registry.complete = Mock()
    with pytest.raises(ValueError):
        run.implement("Task", **kwargs)
    run.provider_registry.complete.assert_not_called()


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True).stdout.strip()


def test_isolated_application_preserves_dirty_source_index_and_branch(tmp_path, monkeypatch):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.name", "Test")
    git(tmp_path, "config", "user.email", "test@example.invalid")
    (tmp_path / "example.py").write_text("committed = True")
    git(tmp_path, "add", "example.py")
    git(tmp_path, "-c", "commit.gpgsign=false", "commit", "-qm", "Initial")
    (tmp_path / "example.py").write_text("user_edit = True")
    git(tmp_path, "add", "example.py")
    (tmp_path / ".env").write_text("PRIVATE=secret")
    before = git(tmp_path, "diff", "--cached")
    branch = git(tmp_path, "branch", "--show-current")
    run = engine(tmp_path)
    from app.providers.demo import DemoProvider
    original = DemoProvider._render

    def render(self, agent, task):
        if agent == "coder":
            return json.dumps({"changes": [{"path": "example.py", "content": "generated = True"}]})
        return original(self, agent, task)

    monkeypatch.setattr(DemoProvider, "_render", render)
    from app.tools.shell import ShellTool
    locations = []

    def validate(shell, command):
        locations.append(shell.root)
        return CommandExecution(command=command, exit_code=0)

    monkeypatch.setattr(ShellTool, "run", validate)
    result = run.implement("Task", apply_changes=True, isolated=True)
    workspace = Path(result.workspace_path)
    assert result.success
    assert (workspace / "example.py").read_text() == "generated = True"
    assert (tmp_path / "example.py").read_text() == "user_edit = True"
    assert git(tmp_path, "diff", "--cached") == before
    assert git(tmp_path, "branch", "--show-current") == branch
    assert git(workspace, "branch", "--show-current") == result.workspace_branch
    assert not (workspace / ".env").exists()
    assert locations == [workspace]


def test_standalone_review_fails_closed(tmp_path):
    run = engine(tmp_path)
    scripted(run, ["Unstructured prose"])
    result = run.review()
    assert not result.success
    assert result.review_status == "invalid"


def test_repair_review_keeps_full_run_diff_and_previous_findings(tmp_path, monkeypatch):
    run = engine(tmp_path)
    original = run.provider_registry.demo._render
    proposals = iter([
        {"changes": [{"path": "first.py", "content": "first = 1"}, {"path": "second.py", "content": "second = 1"}]},
        {"changes": [{"path": "second.py", "content": "second = 2"}]},
    ])
    reviews = iter([report("request_changes"), report()])
    contexts = []
    from app.agents.base import Agent
    original_run = Agent.run

    def capture(agent, task, context):
        if agent.name == "reviewer":
            contexts.append(context)
        return original_run(agent, task, context)

    monkeypatch.setattr(Agent, "run", capture)

    def render(agent, task):
        if agent == "coder":
            return json.dumps(next(proposals))
        if agent == "reviewer":
            return next(reviews)
        return original(agent, task)

    run.provider_registry.demo._render = render
    run.shell.run = Mock(return_value=CommandExecution(command="trusted-test", exit_code=0))
    result = run.implement("Task", apply_changes=True, max_repairs=1)
    assert result.success
    assert "first = 1" in contexts[1]["proposed_or_applied_diff"]
    assert "second = 2" in contexts[1]["proposed_or_applied_diff"]
    assert "request_changes" in contexts[1]["previous_review_output"]
