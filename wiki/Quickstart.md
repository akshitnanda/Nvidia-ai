# Quickstart

## Mission control

Run `swarm dashboard` to launch and monitor workflows. Start with a demo plan or the guided approval-and-repair scenario. The durable queue supports per-job limits, explicit diff approval, cancellation, and fresh retries after interruption. Managed file application uses isolated branches and never auto-commits. See `docs/mission-control.md` for configuration and recovery behavior.

## Isolated coding with repair

```powershell
swarm implement "Add a health endpoint with tests" --isolated --apply --max-repairs 2
```

Start at the Git repository root. Runs use committed `HEAD`, retain a separate `swarm/<run-id>` worktree, and ask for approval before every application. Source checkout edits and secrets are not copied. Validation and structured review must approve before an optional automatic commit. Worktrees are not command sandboxes.

Open `swarm dashboard` to inspect quality gates, repair attempts, findings, command output, and the live execution timeline. Use the Artifacts tab for full evidence. Custom reviewer prompts must follow the JSON schema in `config/prompts/reviewer.md`.

## Windows PowerShell

```powershell
powershell -ExecutionPolicy Bypass -File scripts/bootstrap.ps1
swarm demo
swarm dashboard
```

Then open `http://127.0.0.1:8787/`.

## Cross-platform Python

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m app.cli.app demo
python -m app.cli.app dashboard
```

## Live Mode

To use live NVIDIA inference instead of the scripted demo path:

1. Copy `.env.example` to `.env`.
2. Set `NVIDIA_API_KEY`.
3. Keep `NVIDIA_PROVIDER_MODE=serverless`, or switch to `local_nim` for a compatible local endpoint.

## Local Checks

```powershell
python -m pytest -q
python -m compileall app tests
mkdocs build --strict
```
