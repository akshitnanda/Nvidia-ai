# Architecture Notes

## High-level Flow

```text
CLI / Dashboard
      |
      v
Local Orchestrator
      |
      +-- Agent Registry + Prompt Loader
      +-- Local Tools
      +-- Memory Store + Run Logger
      +-- Provider Registry
              |
              +-- NVIDIA serverless / local NIM
              +-- scripted demo provider
```

## Important Modules

- `app/cli/app.py`
  Exposes the Typer commands, including the dedicated `demo` command.

- `app/orchestrator/engine.py`
  Coordinates repo scanning, agent calls, previews, validation, and artifact logging.

- `app/providers/nvidia.py`
  Handles live NVIDIA-compatible chat completions.

- `app/providers/demo.py`
  Provides deterministic no-key responses for GitHub and onboarding demos.

- `app/api/dashboard.py`
  Serves the local dashboard and run browsing endpoints.

## Config

- `config/models.yaml`
  Model routing and profile settings.

- `config/agents.yaml`
  Agent roles, goals, prompt files, and allowed tools.
