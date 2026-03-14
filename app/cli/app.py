from __future__ import annotations

import json
from pathlib import Path

import typer
import uvicorn
from rich.console import Console
from watchfiles import watch

from app.api.dashboard import create_app
from app.models.runtime import WorkflowMode
from app.models.settings import get_settings
from app.orchestrator.engine import Orchestrator
from app.utils.logging import configure_logging

app = typer.Typer(help="Local-first NVIDIA-only developer swarm.")
console = Console()


def build_orchestrator(root: Path) -> Orchestrator:
    settings = get_settings()
    configure_logging(settings.swarm_log_level)
    return Orchestrator(root=root, settings=settings)


def emit_result(result_json: bool, result: object) -> None:
    if result_json:
        console.print_json(json.dumps(result.model_dump()))
    else:
        console.print(result.summary)
        for key, value in result.outputs.items():
            console.print(f"\n[bold]{key}[/bold]\n{value}")
        if result.changed_files:
            console.print(f"\nChanged files: {', '.join(result.changed_files)}")
        if result.command_results:
            for command_result in result.command_results:
                console.print(
                    f"\n[bold]{command_result.command}[/bold] exit={command_result.exit_code}\n"
                    f"{command_result.stdout or command_result.stderr}"
                )


@app.command("analyze-repo")
def analyze_repo(
    root: Path = typer.Option(Path("."), help="Workspace root."),
    result_json: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    orchestrator = build_orchestrator(root)
    emit_result(result_json, orchestrator.analyze_repo())


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
    uvicorn.run(create_app(root), host=host, port=port)


@app.command("watch-repo")
def watch_repo(
    task: str = typer.Option("Summarize recent changes.", help="Task to run on change."),
    mode: WorkflowMode = typer.Option(WorkflowMode.REVIEW, help="Workflow mode to trigger."),
    root: Path = typer.Option(Path("."), help="Workspace root."),
) -> None:
    console.print(f"Watching {root.resolve()} in {mode.value} mode. Press Ctrl+C to stop.")
    for _changes in watch(str(root)):
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

