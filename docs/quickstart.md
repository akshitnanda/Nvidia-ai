# Quickstart

## Windows

```powershell
powershell -ExecutionPolicy Bypass -File scripts/bootstrap.ps1
swarm demo
swarm dashboard
```

Open `http://127.0.0.1:8787/` after the dashboard starts.

The dashboard now includes **Mission control**: queue a demo plan, or load **Try the approval & repair demo** from a committed Git repository. Managed file application always uses an isolated branch and pauses for every diff approval. See [Mission control](mission-control.md) for execution limits, cancel/retry controls, and restart recovery.

## Cross-platform

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m app.cli.app demo
python -m app.cli.app dashboard
```

On Windows PowerShell, activate with:

```powershell
.venv\Scripts\Activate.ps1
```

## Live NVIDIA Mode

When you are ready to move past the scripted walkthrough:

1. Copy `.env.example` to `.env`.
2. Set `NVIDIA_API_KEY`.
3. Keep `NVIDIA_PROVIDER_MODE=serverless`, or change it to `local_nim` if you are pointing at a compatible local endpoint.

Example:

```powershell
swarm plan "Add a FastAPI health endpoint and tests"
swarm implement "Add a FastAPI health endpoint and tests" --apply
swarm review
```

`local_nim` does not require a cloud API key. Set `NVIDIA_LOCAL_NIM_BASE_URL` to your compatible endpoint.

## Inspect and Validate

```powershell
swarm implement "Add a FastAPI health endpoint and tests"  # preview only
swarm runs
swarm runs <run-id> --json
```

After `--apply` is approved, the workflow runs `SWARM_DEFAULT_TEST_COMMAND` and `SWARM_DEFAULT_LINT_COMMAND`. Suggested commands from the models are saved as advice. Preview runs report `validation_status=not_run`. Failed validation produces a nonzero CLI exit code and prevents automatic commits; `--no-run-tests` also prevents automatic commits.

Open the dashboard and select a run. **Overview** shows quality gates, findings, validation commands, attempt history, and execution events. **Artifacts** contains the full evidence. Live updates refresh every five seconds while the page is visible, or use **Refresh** manually. Search and status filters apply to the latest 100 loaded runs. Both the CLI and dashboard honor `SWARM_DATA_DIR`.

## Isolated implementation and repair

```powershell
swarm implement "Add a health endpoint with tests" --isolated --apply --max-repairs 2
```

Run this from a Git repository root with at least one commit. The workflow creates a retained worktree from committed `HEAD` on a `swarm/<run-id>` branch. Source checkout edits, the source index, untracked files, and `.env` are not copied. Operator configuration remains loaded from the source workspace. Validation uses the existing execution environment with the worktree as its working directory; install dependencies first.

Every repair receives the full applied diff, earlier review findings, and command results. Each proposed repair passes preflight and approval again. `SWARM_AUTO_APPLY` retains its existing policy for small, non-risky changes. Repairs are optional (default zero), with a maximum of three. A no-op or declined repair cannot reset earlier failed validation.

Review output must match the structured JSON schema in `config/prompts/reviewer.md`. Update custom reviewer prompts to use that schema. `request_changes`, critical/high findings, and malformed output all prevent automatic commits and produce a nonzero CLI exit. Low/medium findings may coexist with approval only if the reviewer explicitly approves. Preview review approval does not mean tests ran.

The CLI prints the worktree path and branch. Inspect it with `git -C <workspace-path> diff`; add `--commit-message "Your message"` to commit only when validation and review approve. Integrate the branch yourself after inspection. Worktrees persist after failures for investigation. Git worktrees do not sandbox commands or credentials, and host-mode file writes are not transactional.

## Local Validation

```powershell
python -m pytest -q
python -m compileall app tests
```

If you want to preview the docs site locally:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/docs.ps1
```
