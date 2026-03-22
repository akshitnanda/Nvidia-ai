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

### Config

`config/models.yaml` and `config/agents.yaml` keep routing and agent behavior configurable without changing orchestration code.
