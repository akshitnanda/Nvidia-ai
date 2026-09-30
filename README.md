# NVIDIA Local Dev Swarm

[![CI](https://github.com/akshitnanda/Nvidia-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/akshitnanda/Nvidia-ai/actions/workflows/ci.yml)
[![Docs](https://github.com/akshitnanda/Nvidia-ai/actions/workflows/pages.yml/badge.svg)](https://akshitnanda.github.io/Nvidia-ai/)
[![Release](https://img.shields.io/github/v/release/akshitnanda/Nvidia-ai?display_name=tag)](https://github.com/akshitnanda/Nvidia-ai/releases)

Local-first multi-agent developer workflow for Python repos, with NVIDIA-hosted inference for real runs and a scripted `demo` mode for GitHub walkthroughs.

GitHub:

- Repo: https://github.com/akshitnanda/Nvidia-ai
- Docs: https://akshitnanda.github.io/Nvidia-ai/
- Actions: https://github.com/akshitnanda/Nvidia-ai/actions
- Releases: https://github.com/akshitnanda/Nvidia-ai/releases

## Preview, Apply, Inspect

- **Preview by default:** inspect a complete diff without writing proposed files or running validation commands.
- **Explicit application:** `--apply` shows the diff and asks before writes; validation uses your configured test and lint commands. Model-suggested commands are saved for inspection, never executed automatically.
- **Observable runs:** inspect status, agent events, usage, validation, and artifacts through `swarm runs` or the dashboard.
- **Faster handoffs:** test and documentation agents run concurrently once the code proposal is ready.
- **No-key demo:** `swarm demo` returns scripted local responses; demo token counts are estimates.

See the [engineering assessment](docs/engineering-assessment.md) for the fixes, verification, and remaining limitations.

## Fastest First Run

### Windows PowerShell

```powershell
powershell -ExecutionPolicy Bypass -File scripts/bootstrap.ps1
swarm demo
swarm dashboard
```

Then open `http://127.0.0.1:8787/`.

If you want the docs site locally:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/docs.ps1
```

### Cross-platform Python

```bash
python -m venv .venv
. .venv/bin/activate  # Windows: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m app.cli.app demo
python -m app.cli.app dashboard
```

## Demo Modes

Use demo mode when you want a safe GitHub or screen-share walkthrough:

```powershell
swarm demo --mode analyze
swarm demo --mode plan --task "Add a FastAPI health endpoint"
swarm demo --mode implement --task "Add a FastAPI health endpoint"
```

What demo mode does:

- returns deterministic local responses
- writes run artifacts to `data/runs/`
- avoids real NVIDIA API calls
- keeps `implement` preview-only by default

## Live NVIDIA Mode

When you want real model output instead of the scripted demo path:

1. Copy `.env.example` to `.env` if you have not already.
2. Set `NVIDIA_API_KEY`.
3. Keep `NVIDIA_PROVIDER_MODE=serverless` for NVIDIA-hosted inference, or switch to `local_nim` for a self-hosted compatible endpoint.

Example:

```powershell
swarm plan "Add a FastAPI health endpoint and tests"
swarm implement "Add a FastAPI health endpoint and tests" --apply
swarm review
swarm release --since HEAD~5
```

## Dashboard

The optional FastAPI dashboard exposes:

- `/` for searchable runs and an artifact viewer, with status and token usage
- `/docs` for the Swagger UI
- `/health` for a simple health check
- `/runs` and `/runs/{run_id}` for local run artifacts
- `/runs?details=true&limit=50&offset=0` for paginated run summaries

The dashboard honors `SWARM_DATA_DIR`, handles incomplete artifacts, and serves artifacts as text. It is a read-only local viewer; start workflows from the CLI.

Start it with:

```powershell
swarm dashboard
```

## GitHub Pages Docs

The repo now includes an Actions-based docs site powered by MkDocs.

- source lives under `docs/`
- config lives in `mkdocs.yml`
- `.github/workflows/pages.yml` builds docs on pull requests
- pushes to `main` deploy to GitHub Pages

To preview locally:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/docs.ps1
```

In GitHub, set `Settings` -> `Pages` -> `Source` to `GitHub Actions`.

## Releases

Version tags now publish release assets automatically through `.github/workflows/release.yml`.

Published artifacts include:

- wheel
- source distribution
- zipped docs site
- `SHA256SUMS.txt`
- packaged default config and prompts inside the wheel so the CLI still has a baseline config when installed outside this repo

Automatic path:

```bash
git tag v0.1.0
git push origin v0.1.0
```

Manual path:

- open the `Release` workflow in GitHub Actions
- run `workflow_dispatch`
- provide a tag such as `v0.1.0`

## CLI Commands

```text
swarm analyze-repo
swarm plan "<task>"
swarm implement "<task>" --apply
swarm review
swarm release --since HEAD~5
swarm watch-repo --mode review
swarm dashboard
swarm demo --mode plan
swarm runs
swarm runs <run-id> --json
```

## Architecture At A Glance

```text
CLI / Dashboard
      |
      v
Local Orchestrator
      |
      +-- Agent Registry + Prompt Loader
      +-- Local Tools (repo, git, shell, filesystem)
      +-- Memory Store + Run Logger
      +-- Provider Registry
              |
              +-- NVIDIA serverless / local NIM
              +-- scripted demo provider
```

Key folders:

```text
app/
  agents/
  api/
  cli/
  memory/
  models/
  orchestrator/
  providers/
  tools/
  workflows/
config/
  prompts/
scripts/
tests/
```

## Validation

Run the local checks with:

```powershell
python -m pytest -q
python -m compileall app tests
```

GitHub Actions mirrors the test run on:

- Windows + Python 3.11 / 3.12
- Ubuntu + Python 3.11 / 3.12
- docs build + Pages deploy on `main`
- release packaging on tags matching `v*`

## Notes

- This repo is Windows-friendly first, but the core CLI also works cross-platform.
- Demo mode is intentionally scripted, so it is useful for onboarding and repo previews, not for judging model quality.
- Live runs store artifacts and usage logs under `data/`.
- Workspace-local `config/` still wins, but release artifacts now carry packaged fallback defaults for cleaner installs and demos.

## Execution Rules

- Validation runs only after approved file changes are applied. `validation_status` distinguishes `not_run`, `passed`, and `failed`; a failed validation sets `success=false` and a nonzero CLI exit code.
- Configure `SWARM_DEFAULT_TEST_COMMAND` and `SWARM_DEFAULT_LINT_COMMAND` locally. Review generated code before applying: these commands run on your host, not in a sandbox.
- Automatic commits require completed, passing validation and a completed review call. They stage only the workflow's changed files and refuse to proceed when the index already contains staged changes. Review output remains advisory.
- Repository snapshots respect Git ignore rules, skip common secret paths and external symlinks, and tolerate binary files. Git diffs filter common secret paths too. These filters do not detect credentials embedded in ordinary source files or existing memory.
- Conflicting proposals, workspace escapes, `.git` edits, secret-like paths, missing content, and oversized files are rejected during preflight. File application is not a multi-file transaction; existing files receive uniquely named `.bak` backups.
- Watch mode excludes generated run data, caches, backups, and common secret paths to avoid retriggering itself.
