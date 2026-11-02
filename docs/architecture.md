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

`app/api/dashboard.py` exposes health, run listings, run detail payloads, and the Run control dashboard. HTML, CSS, and JavaScript under `app/api/static/` ship inside the wheel. The browser renders all run content as text, including findings, command output, and artifacts.

The run viewer uses `app/memory/runs.py` for bounded artifact reads and path validation. `/runs` preserves the original run-ID list; `?details=true` adds status, workflow, provider, and usage. Pagination uses `limit` and `offset`.

### Execution and evidence

Implementation follows planner → coder → concurrent tester/docs → combined preflight → optional approved writes → configured validation → structured review → optional bounded repairs → context update → optional scoped commit. Model-suggested shell commands are retained as advice. Preview and declined-approval paths do not execute them or run validation.

Each workflow writes a `run.json` manifest and a `result.json` on completion. Caught exceptions persist a failed manifest; agent outputs are saved as they arrive. `events.jsonl` records agent start, completion, failure, model, and duration. Per-run `usage.jsonl` associates usage with the run, while the aggregate usage log remains available. Manifest writes use a temporary file followed by replacement so a dashboard refresh does not see partial JSON.

Implementation/review success requires a valid structured review approval, with no critical/high findings, and no failed validation. Validation remains separately reported as `not_run`, `passed`, or `failed`; preview approval is not execution evidence. Review is a model judgment, not a correctness or security guarantee. Interrupted processes that cannot run cleanup can leave a manifest marked `running`.

Each implementation attempt persists its changeset, diff, review output, structured result, and validation evidence. `attempts.json` records the sequence, and `applied-change.diff` preserves the cumulative applied diff. Repairs receive that cumulative diff and the earlier review. A no-op or declined repair retains earlier validation evidence. Commits require both passing validation and approved review.

With `--isolated`, `app/tools/workspace.py` creates a retained Git worktree from committed `HEAD` on a run-specific branch. The child orchestrator shares the original run logger, memory store, and operator configuration, but file and shell tools target the worktree. Source edits and secrets are not copied, and the original branch/index stay in place. Isolation is a filesystem workflow boundary, not a command sandbox. Worktrees are never automatically merged or removed.

### Context and write boundaries

Git-backed scans use tracked and nonignored untracked files; non-Git directories use a filesystem walk. Common secret paths, generated directories, binary content, and external symlinks are excluded. Diff collection disables external diff/text conversion and bounds prompt output. Secret filtering is based on paths, not a general content redactor.

Filesystem changes are preflighted together. Duplicate or ancestor/descendant destinations fail before writes. Writes remain host filesystem operations with backups, not a transaction or execution sandbox.

### Config

`config/models.yaml` and `config/agents.yaml` keep routing and agent behavior configurable without changing orchestration code.
