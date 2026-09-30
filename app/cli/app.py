from __future__ import annotations

import json
from pathlib import Path

import typer
import uvicorn
from rich.console import Console
from watchfiles import DefaultFilter, watch

from app.api.dashboard import create_app
from app.models.runtime import WorkflowMode, WorkflowResult
from app.models.settings import get_settings
from app.orchestrator.engine import Orchestrator
from app.utils.logging import configure_logging
from app.tools.paths import excluded_path
from app.memory.runs import RunStore

app = typer.Typer(help="Local-first NVIDIA-only developer swarm.")
console = Console()


def build_orchestrator(root: Path, provider_mode: str | None = None) -> Orchestrator:
    settings = get_settings()
    if provider_mode:
        settings = settings.model_copy(update={"nvidia_provider_mode": provider_mode})
    configure_logging(settings.swarm_log_level)
    return Orchestrator(root=root, settings=settings)


def emit_result(result_json: bool, result: WorkflowResult) -> None:
    if result_json:
        console.print_json(json.dumps(result.model_dump()))
    else:
        console.print(result.summary)
        for key, value in result.outputs.items():
            console.print(f"\n{key}\n{value}", markup=False)
        if result.changed_files:
            console.print(f"\nChanged files: {', '.join(result.changed_files)}")
        if result.command_results:
            for command_result in result.command_results:
                console.print(
                    f"\n[bold]{command_result.command}[/bold] exit={command_result.exit_code}\n"
                    f"{command_result.stdout or command_result.stderr}"
                )
        console.print(f"\nRun: {result.run_id} | Validation: {result.validation_status}")
        if result.suggested_commands:
            console.print("Model-suggested commands (not executed):", markup=False)
            for command in result.suggested_commands:
                console.print(f"  {command}", markup=False)
    if not result.success:
        raise typer.Exit(code=1)


@app.command("analyze-repo")
def analyze_repo(
    root: Path = typer.Option(Path("."), help="Workspace root."),
    result_json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    orchestrator = build_orchestrator(root)
    emit_result(result_json, orchestrator.analyze_repo())


@app.command()
def runs(
    run_id: str | None = typer.Argument(None, help="Inspect one run, including its artifacts."),
    root: Path = typer.Option(Path("."), help="Workspace root."),
    limit: int = typer.Option(20, min=1, max=100),
    result_json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    store = RunStore(root.resolve() / get_settings().swarm_data_dir)
    try:
        payload = store.get(run_id) if run_id else store.list(limit=limit)
    except FileNotFoundError:
        console.print("Run not found.")
        raise typer.Exit(code=1) from None
    if result_json or run_id:
        console.print_json(json.dumps(payload))
    elif not payload:
        console.print("No runs yet. Start with swarm demo.")
    else:
        from rich.table import Table
        table = Table("Run", "Mode", "Status", "Provider", "Tokens")
        for row in payload:
            table.add_row(row["run_id"], row["mode"], row["status"], row.get("provider", "legacy"), str(row["total_tokens"]))
        console.print(table)


@app.command()
def plan(
    task: str = typer.Argument(..., help="Task to plan."),
    root: Path = typer.Option(Path("."), help="Workspace root."),
    result_json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    orchestrator = build_orchestrator(root)
    emit_result(result_json, orchestrator.plan(task))


@app.command()
def implement(
    task: str = typer.Argument(..., help="Task to implement."),
    root: Path = typer.Option(Path("."), help="Workspace root."),
    apply: bool = typer.Option(False, help="Apply file changes after preview/approval."),
    run_tests: bool = typer.Option(True, help="Run validation commands."),
    commit_message: str | None = typer.Option(None, help="Auto-commit message after applied changes."),
    result_json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    orchestrator = build_orchestrator(root)
    emit_result(
        result_json,
        orchestrator.implement(
            task,
            apply_changes=apply,
            run_validation=run_tests,
            commit_message=commit_message,
        ),
    )


@app.command()
def review(
    root: Path = typer.Option(Path("."), help="Workspace root."),
    staged: bool = typer.Option(False, help="Review staged changes instead of working tree."),
    result_json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    orchestrator = build_orchestrator(root)
    emit_result(result_json, orchestrator.review(staged=staged))


@app.command()
def release(
    root: Path = typer.Option(Path("."), help="Workspace root."),
    since: str | None = typer.Option(None, help="Git ref or range start, such as HEAD~5."),
    result_json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    orchestrator = build_orchestrator(root)
    emit_result(result_json, orchestrator.release(since=since))


@app.command()
def dashboard(
    root: Path = typer.Option(Path("."), help="Workspace root."),
    host: str = typer.Option("127.0.0.1", help="Bind host."),
    port: int = typer.Option(8787, help="Bind port."),
) -> None:
    uvicorn.run(create_app(root, settings=get_settings()), host=host, port=port)


@app.command()
def demo(
    mode: WorkflowMode = typer.Option(WorkflowMode.ANALYZE, help="Workflow to run with deterministic local output."),
    task: str = typer.Option(
        "Show how this project works from a fresh GitHub checkout.",
        help="Task used for plan or implement demos.",
    ),
    root: Path = typer.Option(Path("."), help="Workspace root."),
    result_json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    orchestrator = build_orchestrator(root, provider_mode="demo")
    if mode == WorkflowMode.ANALYZE:
        result = orchestrator.analyze_repo()
    elif mode == WorkflowMode.PLAN:
        result = orchestrator.plan(task)
    elif mode == WorkflowMode.IMPLEMENT:
        result = orchestrator.implement(task, apply_changes=False, run_validation=False)
    elif mode == WorkflowMode.RELEASE:
        result = orchestrator.release()
    else:
        result = orchestrator.review()
    emit_result(result_json, result)


@app.command("watch-repo")
def watch_repo(
    task: str = typer.Option("Summarize recent changes.", help="Task to run on change."),
    mode: WorkflowMode = typer.Option(WorkflowMode.REVIEW, help="Workflow mode to trigger."),
    root: Path = typer.Option(Path("."), help="Workspace root."),
) -> None:
    console.print(f"Watching {root.resolve()} in {mode.value} mode. Press Ctrl+C to stop.")
    data_dir = (root / get_settings().swarm_data_dir).resolve()
    default_filter = DefaultFilter()

    def watch_filter(change: object, path: str) -> bool:
        candidate = Path(path).resolve()
        return (default_filter(change, path) and candidate.is_relative_to(root.resolve())
                and not candidate.is_relative_to(data_dir)
                and not excluded_path(candidate.relative_to(root.resolve())))

    for _changes in watch(str(root), watch_filter=watch_filter):
        orchestrator = build_orchestrator(root)
        if mode == WorkflowMode.ANALYZE:
            result = orchestrator.analyze_repo()
        elif mode == WorkflowMode.PLAN:
            result = orchestrator.plan(task)
        elif mode == WorkflowMode.IMPLEMENT:
            result = orchestrator.implement(task, apply_changes=False, run_validation=False)
        elif mode == WorkflowMode.RELEASE:
            result = orchestrator.release()
        else:
            result = orchestrator.review()
        emit_result(False, result)


if __name__ == "__main__":
    app()
