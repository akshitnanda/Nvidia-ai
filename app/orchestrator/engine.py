from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from app.agents.registry import AgentRegistry
from app.memory.context import render_recent_memory
from app.memory.store import MemoryStore
from app.models.config import load_agents_config, load_models_config
from app.models.runtime import AgentResult, ChangeSet, WorkflowMode, WorkflowResult
from app.models.settings import Settings
from app.orchestrator.approvals import ApprovalGate
from app.providers.factory import ProviderRegistry
from app.tools.filesystem import FileSystemTool
from app.tools.git_tools import GitTool
from app.tools.repo import RepoScanner
from app.tools.shell import ShellTool
from app.utils.logging import RunLogger
from app.utils.patches import PreviewChange, extract_json_block


class Orchestrator:
    """Coordinates local tools, agents, approvals, and artifacts."""

    def __init__(self, root: Path, settings: Settings) -> None:
        self.root = root.resolve()
        self.settings = settings
        self.config_dir = (self.root / settings.swarm_config_dir).resolve()
        self.data_dir = (self.root / settings.swarm_data_dir).resolve()
        self.run_logger = RunLogger(self.data_dir)
        self.memory = MemoryStore(self.data_dir / "memory.sqlite3")
        self.models_config = load_models_config(self.config_dir)
        self.agents_config = load_agents_config(self.config_dir)
        self.provider_registry = ProviderRegistry(settings, self.models_config, self.run_logger)
        self.agents = AgentRegistry(
            config_dir=self.config_dir,
            agents_config=self.agents_config,
            models_config=self.models_config,
            provider_registry=self.provider_registry,
        )
        self.fs = FileSystemTool(self.root, max_file_bytes=settings.swarm_max_file_bytes)
        self.git = GitTool(self.root)
        self.repo = RepoScanner(self.root, max_file_bytes=settings.swarm_max_file_bytes)
        self.shell = ShellTool(self.root)
        self.rules_text = (self.config_dir / "rules.md").read_text(encoding="utf-8")

    def _build_context(self, task: str, mode: WorkflowMode) -> dict[str, Any]:
        return {
            "mode": mode.value,
            "root": str(self.root),
            "repo_tree": self.repo.tree(),
            "focused_files": self.repo.focused_snapshot(task, limit=self.settings.swarm_max_focused_files),
            "git_status": self.git.status(),
            "git_diff": self.git.diff(),
            "recent_commits": self.git.recent_commits(),
            "rules": self.rules_text,
            "memory": render_recent_memory(self.memory),
        }

    def _parse_changeset(self, result: AgentResult) -> ChangeSet:
        payload = extract_json_block(result.output)
        return ChangeSet.model_validate(payload)

    def _preview_changes(self, changeset: ChangeSet) -> list[PreviewChange]:
        return [self.fs.preview_change(change) for change in changeset.changes]

    def _apply_changes(self, changeset: ChangeSet) -> list[str]:
        changed_files: list[str] = []
        for change in changeset.changes:
            changed_files.append(str(self.fs.apply_change(change).relative_to(self.root).as_posix()))
        return changed_files

    def analyze_repo(self) -> WorkflowResult:
        context = self._build_context("Analyze the current repository.", WorkflowMode.ANALYZE)
        agent_result = self.agents.get("context").run("Analyze the current repository.", context)
        self.memory.add_entry("context", "repo", agent_result.output[:2000], {"model": agent_result.model})
        self.run_logger.write_text("context.md", agent_result.output)
        return WorkflowResult(
            run_id=self.run_logger.run_id,
            mode=WorkflowMode.ANALYZE,
            success=True,
            summary="Repository analysis complete.",
            outputs={"context": agent_result.output},
        )

    def plan(self, task: str) -> WorkflowResult:
        context = self._build_context(task, WorkflowMode.PLAN)
        planner = self.agents.get("planner").run(task, context)
        self.memory.add_entry("plan", "task", planner.output[:2000], {"task": task, "model": planner.model})
        self.run_logger.write_text("plan.md", planner.output)
        return WorkflowResult(
            run_id=self.run_logger.run_id,
            mode=WorkflowMode.PLAN,
            success=True,
            summary="Plan generated.",
            outputs={"plan": planner.output},
        )

    def implement(
        self,
        task: str,
        apply_changes: bool = False,
        run_validation: bool = True,
        commit_message: str | None = None,
    ) -> WorkflowResult:
        context = self._build_context(task, WorkflowMode.IMPLEMENT)
        planner_result = self.agents.get("planner").run(task, context)
        coder_context = {**context, "planner_output": planner_result.output}
        coder_result = self.agents.get("coder").run(task, coder_context)
        code_changes = self._parse_changeset(coder_result)

        diff_preview = "\n\n".join(preview.diff for preview in self._preview_changes(code_changes))
        test_context = {**coder_context, "proposed_code_diff": diff_preview}
        docs_context = {**coder_context, "proposed_code_diff": diff_preview}

        tester_result = self.agents.get("tester").run(task, test_context)
        docs_result = self.agents.get("docs").run(task, docs_context)
        test_changes = self._parse_changeset(tester_result)
        docs_changes = self._parse_changeset(docs_result)

        combined_changes = ChangeSet(
            summary="\n".join(
                filter(None, [code_changes.summary, test_changes.summary, docs_changes.summary])
            ),
            changes=[*code_changes.changes, *test_changes.changes, *docs_changes.changes],
            commands=list(dict.fromkeys([*code_changes.commands, *test_changes.commands, *docs_changes.commands])),
        )
        previews = self._preview_changes(combined_changes)
        preview_text = "\n\n".join(preview.diff or f"# No diff for {preview.path}" for preview in previews)
        self.run_logger.write_text("change-preview.diff", preview_text)

        gate = ApprovalGate(auto_apply=self.settings.swarm_auto_apply, interactive=apply_changes)
        changed_files: list[str] = []
        commit_output = ""
        if apply_changes and gate.should_apply(previews):
            changed_files = self._apply_changes(combined_changes)

        command_results = []
        if run_validation:
            commands = combined_changes.commands or [self.settings.swarm_default_test_command]
            for command in commands:
                command_results.append(self.shell.run(command))

        if commit_message and changed_files:
            validations_ok = all(result.exit_code == 0 for result in command_results) if run_validation else True
            if validations_ok:
                commit_output = self.git.commit(commit_message)
            else:
                commit_output = "Skipping commit because one or more validation commands failed."
            self.run_logger.write_text("commit.txt", commit_output)

        review_context = {
            **context,
            "planner_output": planner_result.output,
            "proposed_or_applied_diff": preview_text,
            "validation_results": [result.model_dump() for result in command_results],
            "commit_output": commit_output,
        }
        with ThreadPoolExecutor(max_workers=2) as pool:
            review_future = pool.submit(self.agents.get("reviewer").run, task, review_context)
            context_future = pool.submit(self.agents.get("context").run, f"Update repo memory for: {task}", context)
            reviewer_result = review_future.result()
            context_result = context_future.result()

        self.memory.add_entry("decision", "implement", planner_result.output[:2000], {"task": task})
        self.memory.add_entry("review", "implement", reviewer_result.output[:2000], {"task": task})
        self.memory.add_entry("context", "repo", context_result.output[:2000], {"task": task})

        self.run_logger.write_text("plan.md", planner_result.output)
        self.run_logger.write_text("coder-output.md", coder_result.output)
        self.run_logger.write_text("tester-output.md", tester_result.output)
        self.run_logger.write_text("docs-output.md", docs_result.output)
        self.run_logger.write_text("review.md", reviewer_result.output)
        self.run_logger.write_json("validation.json", [result.model_dump() for result in command_results])

        outputs = {
            "plan": planner_result.output,
            "review": reviewer_result.output,
            "preview_diff": preview_text,
        }
        if commit_output:
            outputs["commit"] = commit_output

        return WorkflowResult(
            run_id=self.run_logger.run_id,
            mode=WorkflowMode.IMPLEMENT,
            success=True,
            summary=combined_changes.summary or "Implementation workflow complete.",
            outputs=outputs,
            changed_files=changed_files,
            command_results=command_results,
        )

    def review(self, staged: bool = False) -> WorkflowResult:
        diff_text = self.git.diff(staged=staged)
        context = self._build_context("Review the current git diff.", WorkflowMode.REVIEW)
        context["git_diff"] = diff_text
        reviewer = self.agents.get("reviewer").run("Review the current git diff.", context)
        self.run_logger.write_text("review.md", reviewer.output)
        self.memory.add_entry("review", "diff", reviewer.output[:2000], {"staged": staged})
        return WorkflowResult(
            run_id=self.run_logger.run_id,
            mode=WorkflowMode.REVIEW,
            success=True,
            summary="Review complete.",
            outputs={"review": reviewer.output},
        )

    def release(self, since: str | None = None) -> WorkflowResult:
        scope = f"Generate release notes for changes since {since}." if since else "Generate release notes for recent work."
        context = self._build_context(scope, WorkflowMode.RELEASE)
        if since and self.git.is_repo():
            context["git_diff"] = self.shell.run(f"git diff {since}..HEAD").stdout
            context["recent_commits"] = self.shell.run(f"git log {since}..HEAD --oneline --decorate").stdout
        release_result = self.agents.get("release").run(scope, context)
        self.run_logger.write_text("release-notes.md", release_result.output)
        return WorkflowResult(
            run_id=self.run_logger.run_id,
            mode=WorkflowMode.RELEASE,
            success=True,
            summary="Release notes generated.",
            outputs={"release_notes": release_result.output},
        )
