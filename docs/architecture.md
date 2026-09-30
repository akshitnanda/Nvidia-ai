# Architecture

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

## Core Pieces

### CLI

`app/cli/app.py` exposes the developer-facing workflows and the dedicated `demo` command.

### Orchestrator

`app/orchestrator/engine.py` coordinates context gathering, agent calls, diff previews, validation commands, and artifact logging.

### Providers

- `app/providers/nvidia.py` handles live NVIDIA-compatible chat completions.
- `app/providers/demo.py` handles deterministic local responses for GitHub walkthroughs.

### Dashboard

`app/api/dashboard.py` exposes health, run listings, run detail payloads, and a lightweight landing page for browser demos.

The run viewer uses `app/memory/runs.py` for bounded artifact reads and path validation. `/runs` preserves the original run-ID list; `?details=true` adds status, workflow, provider, and usage. Pagination uses `limit` and `offset`.

### Execution and evidence

Implementation follows planner → coder → concurrent tester/docs → combined preflight → optional approved writes → configured validation → concurrent reviewer/context → optional scoped commit. Model-suggested shell commands are retained as advice. Preview and declined-approval paths do not execute them or run validation.

Each workflow writes a `run.json` manifest and a `result.json` on completion. Caught exceptions persist a failed manifest; agent outputs are saved as they arrive. `events.jsonl` records agent start, completion, failure, model, and duration. Per-run `usage.jsonl` associates usage with the run, while the aggregate usage log remains available. Manifest writes use a temporary file followed by replacement so a dashboard refresh does not see partial JSON.

Workflow success describes completion of orchestration and any executed validation; it is not an automated judgment of review prose. Validation is separately reported as `not_run`, `passed`, or `failed`. Interrupted processes that cannot run cleanup can leave a manifest marked `running`.

### Context and write boundaries

Git-backed scans use tracked and nonignored untracked files; non-Git directories use a filesystem walk. Common secret paths, generated directories, binary content, and external symlinks are excluded. Diff collection disables external diff/text conversion and bounds prompt output. Secret filtering is based on paths, not a general content redactor.

Filesystem changes are preflighted together. Duplicate or ancestor/descendant destinations fail before writes. Writes remain host filesystem operations with backups, not a transaction or execution sandbox.

### Config

`config/models.yaml` and `config/agents.yaml` keep routing and agent behavior configurable without changing orchestration code.
