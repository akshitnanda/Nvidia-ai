from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import sys
from pathlib import Path
from typing import Any

from app.agents.registry import AgentRegistry
from app.memory.context import render_recent_memory
from app.memory.store import MemoryStore
from app.models.config import load_agents_config, load_models_config
from app.models.runtime import AgentResult, ChangeSet, ImplementationAttempt, ReviewReport, WorkflowMode, WorkflowResult
from app.models.settings import Settings, resolve_config_dir
from app.orchestrator.approvals import ApprovalGate
from app.orchestrator.tracking import tracked
from app.providers.factory import ProviderRegistry
from app.tools.filesystem import FileSystemTool
from app.tools.git_tools import GitTool
from app.tools.repo import RepoScanner
from app.tools.shell import ShellTool
from app.tools.workspace import IsolatedWorkspace
from app.utils.logging import RunLogger
from app.utils.patches import PreviewChange, build_unified_diff, extract_json_block


class Orchestrator:
    """Coordinates local tools, agents, approvals, and artifacts."""

    def __init__(self, root: Path, settings: Settings, run_logger: RunLogger | None = None) -> None:
        self.root = root.resolve()
        self.settings = settings
        self.config_dir = resolve_config_dir(self.root, settings.swarm_config_dir)
        self.data_dir = (self.root / settings.swarm_data_dir).resolve()
        self.run_logger = run_logger or RunLogger(self.data_dir)
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
        self.repo = RepoScanner(self.root, max_file_bytes=settings.swarm_max_file_bytes, excluded_dirs=(self.data_dir,))
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
        seen: set[Path] = set()
        for change in changeset.changes:
            path = self.fs.resolve(change.path)
            if path in seen or any(path.is_relative_to(other) or other.is_relative_to(path) for other in seen):
                raise ValueError(f"Conflicting proposed file changes: {change.path}")
            seen.add(path)
        return [self.fs.preview_change(change) for change in changeset.changes]

    def _apply_changes(self, changeset: ChangeSet) -> list[str]:
        self._preview_changes(changeset)
        changed_files: list[str] = []
        for change in changeset.changes:
            changed_files.append(str(self.fs.apply_change(change).relative_to(self.root).as_posix()))
        return changed_files

    @tracked("analyze")
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

    @tracked("plan")
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

    def _review_report(self, result: AgentResult) -> tuple[ReviewReport | None, str]:
        try:
            report = ReviewReport.model_validate(extract_json_block(result.output))
        except ValueError:
            return None, "invalid"
        return report, "approved" if report.approved else "changes_requested"

    @tracked("implement")
    def implement(
        self,
        task: str,
        apply_changes: bool = False,
        run_validation: bool = True,
        commit_message: str | None = None,
        isolated: bool = False,
        max_repairs: int = 0,
    ) -> WorkflowResult:
        if not 0 <= max_repairs <= 3:
            raise ValueError("max_repairs must be between 0 and 3.")
        if max_repairs and not apply_changes:
            raise ValueError("Repair attempts require explicit file application.")
        engine = self
        if isolated:
            workspace = IsolatedWorkspace.create(self.root, self.data_dir, self.run_logger.run_id)
            self.run_logger.manifest.update(workspace_path=str(workspace.path), workspace_branch=workspace.branch,
                                            base_commit=workspace.base_commit, source_root=str(self.root))
            self.run_logger.write_json("run.json", self.run_logger.manifest)
            self.run_logger.event("workspace", "created", path=str(workspace.path), branch=workspace.branch)
            # Keep operator configuration and run evidence outside the generated worktree.
            settings = self.settings.model_copy(update={"swarm_data_dir": self.data_dir,
                                                        "swarm_config_dir": self.config_dir})
            engine = Orchestrator(workspace.path, settings, run_logger=self.run_logger)
        return engine._implement(task, apply_changes, run_validation, commit_message, max_repairs)

    def _implement(self, task: str, apply_changes: bool, run_validation: bool,
                   commit_message: str | None, max_repairs: int) -> WorkflowResult:
        context = self._build_context(task, WorkflowMode.IMPLEMENT)
        planner_result = self.agents.get("planner").run(task, context)
        coder_context = {**context, "planner_output": planner_result.output}
        coder_result = self.agents.get("coder").run(task, coder_context)
        code_changes = self._parse_changeset(coder_result)
        self.run_logger.write_text("plan.md", planner_result.output)
        diff_preview = "\n\n".join(preview.diff for preview in self._preview_changes(code_changes))
        proposal_context = {**coder_context, "proposed_code_diff": diff_preview}
        with ThreadPoolExecutor(max_workers=2) as pool:
            tester_future = pool.submit(self.agents.get("tester").run, task, proposal_context)
            docs_future = pool.submit(self.agents.get("docs").run, task, proposal_context)
            test_changes = self._parse_changeset(tester_future.result())
            docs_changes = self._parse_changeset(docs_future.result())
        changeset = ChangeSet(
            summary="\n".join(filter(None, [code_changes.summary, test_changes.summary, docs_changes.summary])),
            changes=[*code_changes.changes, *test_changes.changes, *docs_changes.changes],
            commands=list(dict.fromkeys([*code_changes.commands, *test_changes.commands, *docs_changes.commands])),
        )
        changed_files: list[str] = []
        suggested_commands = list(changeset.commands)
        attempts: list[ImplementationAttempt] = []
        gate = ApprovalGate(auto_apply=self.settings.swarm_auto_apply, interactive=apply_changes)
        application_status = "not_requested"
        review_context = context
        originals: dict[str, str] = {}
        reviewer_result: AgentResult | None = None
        for number in range(1, max_repairs + 2):
            self.run_logger.event("attempt", "running", attempt=number)
            previews = self._preview_changes(changeset)
            for preview in previews:
                path = preview.path.relative_to(self.root).as_posix()
                if path not in originals:
                    originals[path] = self.fs.read_text(path) if preview.path.exists() else ""
            preview_text = "\n\n".join(preview.diff or f"# No diff for {preview.path}" for preview in previews)
            self.run_logger.write_text(f"attempt-{number}-preview.diff", preview_text)
            self.run_logger.write_json(f"attempt-{number}-changeset.json", changeset)
            self.run_logger.write_text("change-preview.diff", preview_text)
            self.run_logger.write_json("changeset.json", changeset)
            applied: list[str] = []
            if apply_changes:
                print(f"Attempt {number}\n{preview_text or 'No file changes proposed.'}", file=sys.stderr)
                if previews and gate.should_apply(previews):
                    applied = self._apply_changes(changeset)
                    application_status = "applied"
                    changed_files = list(dict.fromkeys([*changed_files, *applied]))
                elif previews:
                    application_status = "declined"
                elif not changed_files:
                    application_status = "no_changes"
            # A no-op or declined repair cannot erase earlier validation evidence.
            command_results = list(attempts[-1].command_results) if attempts and not applied else []
            if run_validation and applied:
                commands = list(dict.fromkeys(filter(None, [self.settings.swarm_default_test_command,
                                                           self.settings.swarm_default_lint_command])))
                for command in commands:
                    self.run_logger.event("validation", "running", command=command, attempt=number)
                    execution = self.shell.run(command)
                    command_results.append(execution)
                    self.run_logger.event("validation", "succeeded" if execution.exit_code == 0 else "failed",
                                          command=command, exit_code=execution.exit_code, attempt=number)
            validation_status = "not_run" if not command_results else (
                "passed" if all(result.exit_code == 0 for result in command_results) else "failed")
            # Review the entire applied change, including files untouched by a repair.
            review_diff = preview_text
            if changed_files:
                review_diff = "\n\n".join(
                    build_unified_diff(Path(path), originals[path],
                                       self.fs.read_text(path) if self.fs.resolve(path).exists() else "")
                    for path in changed_files
                )
                self.run_logger.write_text("applied-change.diff", review_diff)
            review_context = {
                **self._build_context(task, WorkflowMode.IMPLEMENT), "planner_output": planner_result.output,
                "proposed_or_applied_diff": review_diff, "changes_applied": bool(applied),
                "previous_review_output": reviewer_result.output if reviewer_result else None,
                "validation_results": [result.model_dump() for result in command_results],
                "validation_status": validation_status, "attempt": number,
            }
            reviewer_result = self.agents.get("reviewer").run(task, review_context)
            report, review_status = self._review_report(reviewer_result)
            attempt = ImplementationAttempt(number=number, changed_files=applied, validation_status=validation_status,
                                            review_status=review_status, review=report, command_results=command_results)
            attempts.append(attempt)
            self.run_logger.write_json(f"attempt-{number}.json", attempt)
            self.run_logger.write_text(f"attempt-{number}-review.md", reviewer_result.output)
            self.run_logger.write_json("attempts.json", attempts)
            self.run_logger.write_text("review.md", reviewer_result.output)
            self.run_logger.write_json("review.json", report.model_dump() if report else {"status": "invalid"})
            self.run_logger.write_json("validation.json", command_results)
            self.run_logger.manifest.update(changed_files=changed_files, review_status=review_status,
                                            validation_status=validation_status, attempt_count=number,
                                            application_status=application_status)
            self.run_logger.write_json("run.json", self.run_logger.manifest)
            passed = review_status == "approved" and validation_status != "failed"
            self.run_logger.event("attempt", "succeeded" if passed else "failed", attempt=number)
            if passed or not applied or number > max_repairs:
                break
            # Every repair is proposed, preflighted, and approved independently.
            repair_files = {}
            for path in changed_files[:self.settings.swarm_max_focused_files]:
                if self.fs.resolve(path).exists():
                    repair_files[path] = self.fs.read_text(path)
            repair_context = {**review_context, "review_output": reviewer_result.output,
                              "review_report": report.model_dump() if report else None,
                              "repair_files": repair_files,
                              "repair_instruction": "Fix the validation failures and review findings. Return a complete ChangeSet JSON. "
                                                    "Use full contents for each changed file. Do not repeat unchanged files."}
            repaired = self.agents.get("coder").run(task, repair_context)
            self.run_logger.write_text(f"attempt-{number + 1}-coder.md", repaired.output)
            changeset = self._parse_changeset(repaired)
            suggested_commands = list(dict.fromkeys([*suggested_commands, *changeset.commands]))
        final = attempts[-1]
        context_result = self.agents.get("context").run(f"Update repo memory for: {task}", review_context)
        self.memory.add_entry("decision", "implement", planner_result.output[:2000], {"task": task})
        self.memory.add_entry("review", "implement", reviewer_result.output[:2000], {"task": task})
        self.memory.add_entry("context", "repo", context_result.output[:2000], {"task": task})
        commit_output = ""
        if commit_message and changed_files:
            if final.validation_status == "passed" and final.review_status == "approved" and application_status == "applied":
                commit_output = self.git.commit(commit_message, changed_files)
            else:
                commit_output = "Skipping commit because validation failed or did not run, review did not approve, or application was declined."
            self.run_logger.write_text("commit.txt", commit_output)
        outputs = {"plan": planner_result.output, "review": reviewer_result.output, "preview_diff": review_diff}
        if commit_output:
            outputs["commit"] = commit_output
        success = final.review_status == "approved" and final.validation_status != "failed"
        if changed_files and application_status == "declined":
            success = False
        summary = "Implementation needs attention; inspect review and validation."
        if success:
            summary = "Review approved; validation not run."
            if final.validation_status == "passed":
                summary = "Implementation validation and review passed."
            elif application_status == "declined":
                summary = "Application declined; proposal review approved."
        return WorkflowResult(
            run_id=self.run_logger.run_id, mode=WorkflowMode.IMPLEMENT, success=success,
            summary=summary + f" {len(attempts)} attempt(s).",
            outputs=outputs, changed_files=changed_files, command_results=final.command_results,
            validation_status=final.validation_status, suggested_commands=suggested_commands,
            review_status=final.review_status, review=final.review, attempts=attempts,
            application_status=application_status,
            workspace_path=self.run_logger.manifest.get("workspace_path"),
            workspace_branch=self.run_logger.manifest.get("workspace_branch"),
        )

    @tracked("review")
    def review(self, staged: bool = False) -> WorkflowResult:
        diff_text = self.git.diff(staged=staged)
        context = self._build_context("Review the current git diff.", WorkflowMode.REVIEW)
        context["git_diff"] = diff_text
        reviewer = self.agents.get("reviewer").run("Review the current git diff.", context)
        self.run_logger.write_text("review.md", reviewer.output)
        self.memory.add_entry("review", "diff", reviewer.output[:2000], {"staged": staged})
        report, review_status = self._review_report(reviewer)
        self.run_logger.write_json("review.json", report.model_dump() if report else {"status": "invalid"})
        return WorkflowResult(
            run_id=self.run_logger.run_id,
            mode=WorkflowMode.REVIEW,
            success=review_status == "approved",
            summary="Review complete.",
            review=report, review_status=review_status,
            outputs={"review": reviewer.output},
        )

    @tracked("release")
    def release(self, since: str | None = None) -> WorkflowResult:
        scope = f"Generate release notes for changes since {since}." if since else "Generate release notes for recent work."
        context = self._build_context(scope, WorkflowMode.RELEASE)
        if since and self.git.is_repo():
            context["git_diff"] = self.git.diff(revision=since)
            context["recent_commits"] = self.git.commits_since(since)
        release_result = self.agents.get("release").run(scope, context)
        self.run_logger.write_text("release-notes.md", release_result.output)
        return WorkflowResult(
            run_id=self.run_logger.run_id,
            mode=WorkflowMode.RELEASE,
            success=True,
            summary="Release notes generated.",
            outputs={"release_notes": release_result.output},
        )
