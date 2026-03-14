# NVIDIA Local Dev Swarm

## 1. Executive Summary

This project is a local-first, Windows-friendly multi-agent developer workflow that uses only NVIDIA-hosted APIs for cloud inference and can optionally target local NVIDIA NIM endpoints when you want an even more local feel. The MVP is CLI-first, stores run history and project memory locally in SQLite, previews file changes before applying them, integrates with local git and test commands, and keeps model routing fully config-driven so you can swap NVIDIA-supported endpoints without rewriting the orchestration code.

The system is designed for a single developer who wants a practical "local copilot swarm" made up of planner, coder, reviewer, tester, docs, release-notes, and context agents. It favors an extensible but lean architecture: local orchestration runtime, local file and subprocess tools, optional watch mode, optional FastAPI dashboard, and local logs/artifacts under `data/`.

## 2. Architecture Diagram In ASCII

```text
                         +---------------------------+
                         |        VS Code / CLI      |
                         |  swarm plan|implement...  |
                         +-------------+-------------+
                                       |
                                       v
                         +---------------------------+
                         |      Local Orchestrator   |
                         |   run engine + approvals  |
                         +-------------+-------------+
                                       |
             +-------------------------+--------------------------+
             |                         |                          |
             v                         v                          v
  +-------------------+    +------------------------+   +--------------------+
  | Agent Registry    |    | Local Tools            |   | Memory / Run Store |
  | planner           |    | repo scan              |   | SQLite             |
  | coder             |    | filesystem preview     |   | run artifacts      |
  | reviewer          |    | git diff/log           |   | repo notes         |
  | tester            |    | subprocess tests/lint  |   +--------------------+
  | docs              |    | watcher                |
  | release           |    +------------------------+
  | context           |
  +---------+---------+
            |
            v
  +--------------------------+
  | NVIDIA Provider Layer    |
  | config-driven routing    |
  | retries / fallbacks      |
  | usage logging            |
  +-----------+--------------+
              |
      +-------+-----------------------------+
      |                                     |
      v                                     v
+---------------------------+     +---------------------------+
| NVIDIA API Catalog        |     | Optional Local NVIDIA NIM |
| https://integrate.../v1   |     | http://localhost:8000/v1  |
| serverless / trial access |     | self-hosted compatible    |
+---------------------------+     +---------------------------+
```

## 3. Folder Structure

```text
project-root/
  app/
    agents/
    api/
    cli/
    memory/
    models/
    orchestrator/
    providers/
    tools/
    utils/
    workflows/
  config/
    prompts/
  scripts/
  tests/
  .env.example
  .gitignore
  README.md
  pyproject.toml
```

## 4. Tech Stack Decisions And Why

- Python 3.11+: modern typing, broad Windows support, simple subprocess and file tooling.
- Typer: fast CLI UX for local developer workflows.
- FastAPI: optional lightweight dashboard and local API surface.
- HTTPX: clean retryable HTTP client for NVIDIA API calls.
- Pydantic + YAML: strict config and runtime models without overengineering.
- SQLite: local memory, run history, and no extra infrastructure.
- Watchfiles: local folder watch mode for repo-aware workflows.
- Unified diffs + backup writes: safer local editing experience with preview-first behavior.

## 5. NVIDIA API Provider Design

The provider layer lives behind `app/providers/` and never hardcodes a single model in the orchestration logic. `config/models.yaml` defines:

- a catalog of allowed NVIDIA-served models
- profile-level routing like `planner`, `coder`, `reviewer`
- fallback chains per profile
- endpoint style: serverless API Catalog or local NIM

The implementation uses the NVIDIA OpenAI-compatible chat completions surface:

- Serverless base URL: `https://integrate.api.nvidia.com/v1`
- Local NIM default base URL: `http://localhost:8000/v1`
- Endpoint: `POST /chat/completions`

This matches current NVIDIA documentation and API reference:

- NVIDIA LLM API reference: https://docs.api.nvidia.com/nim/reference/llm-apis
- NVIDIA chat completions reference: https://docs.api.nvidia.com/nim/reference/google-codegemma-7b-infer
- NVIDIA model catalog: https://build.nvidia.com/models
- NVIDIA Nemotron 3 Super model page: https://build.nvidia.com/nvidia/nemotron-3-super-120b-a12b/modelcard
- Mistral-Nemotron model page: https://build.nvidia.com/mistralai/mistral-nemotron/modelcard

Current default profiles prefer NVIDIA API Catalog trial-access/serverless options first where available, but every profile can be redirected to another NVIDIA-supported endpoint later in `config/models.yaml`.

## 6. Agent Definitions And Prompts

Each agent is defined in `config/agents.yaml` with:

- role
- goal
- system prompt file
- allowed tool list
- model profile
- approval sensitivity

Implemented agents:

- Planner Agent: decomposes work and chooses execution order.
- Coder Agent: proposes source-code file changes in structured JSON.
- Reviewer Agent: critiques diffs and highlights risk.
- Test Agent: proposes tests and can suggest commands.
- Docs Agent: updates README, docs, and notes.
- Release Notes Agent: turns diffs or commits into changelog text.
- Context Agent: summarizes repo structure, standards, and recent decisions into local memory.

## 7. Orchestration Flow

### PLAN mode

1. Scan repository and focused files.
2. Read local memory and repo rules.
3. Ask Context Agent for a concise repo summary if needed.
4. Ask Planner Agent for a task plan.
5. Save artifacts to `data/runs/<run-id>/`.

### IMPLEMENT mode

1. Build repo context and execution plan.
2. Ask Coder Agent for structured source-file changes.
3. Ask Test Agent and Docs Agent for complementary changes.
4. Preview diffs locally before writing.
5. Require approval for risky or multi-file changes unless `--apply` plus auto-apply is enabled.
6. Apply writes with backups.
7. Run tests or lint locally.
8. Ask Reviewer Agent for a final review summary.
9. Persist outputs, diffs, and decisions to local memory.

### REVIEW mode

1. Inspect current git diff.
2. Ask Reviewer Agent for findings.
3. Store review artifact locally.

### RELEASE mode

1. Collect commits or diff text from git.
2. Ask Release Agent for a changelog / PR summary.
3. Save result to run artifacts.

## 8. Step-By-Step Implementation Plan

1. Create the config-driven project skeleton and install dependencies.
2. Load environment and YAML config for models and agents.
3. Implement the NVIDIA provider with retry, timeout, fallback, and usage logging.
4. Implement local filesystem, git, shell, and repo-scan tools.
5. Implement SQLite-backed memory and run history.
6. Implement agent registry and prompt loading.
7. Implement orchestrator flows for `analyze-repo`, `plan`, `implement`, `review`, and `release`.
8. Add watch mode, VS Code tasks, and optional FastAPI dashboard.
9. Add tests for config loading, memory store, and patch preview behavior.

## 9. Full Scaffolded Code

The scaffolded code lives in the repository and is organized by concern. Start with:

- `app/cli/app.py`
- `app/orchestrator/engine.py`
- `app/providers/nvidia.py`
- `config/models.yaml`
- `config/agents.yaml`

## 10. Setup Instructions For Windows + Optional WSL2

### Windows Native

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .[dev]
Copy-Item .env.example .env
```

Then set `NVIDIA_API_KEY` in `.env`.

### Optional WSL2

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

If you run a local NIM inside WSL2 or Docker, point `NVIDIA_PROVIDER_MODE=local_nim` and set `NVIDIA_LOCAL_NIM_BASE_URL`.

## 11. Example Commands

```powershell
swarm analyze-repo
swarm plan "Add a FastAPI health endpoint and tests"
swarm implement "Add a FastAPI health endpoint and tests" --apply
swarm implement "Add a FastAPI health endpoint and tests" --apply --commit-message "feat: add health endpoint"
swarm review
swarm release --since HEAD~5
swarm watch-repo --mode review
swarm dashboard
```

## 12. Future Upgrades

- Add structured function-calling once the chosen NVIDIA endpoint supports the exact schema you want.
- Add richer repo-memory retrieval with local embeddings or reranking.
- Add multi-run manager mode for batch tasks.
- Add policy packs per repository.
- Add branch management and stricter commit policies on top of the current optional auto-commit flow.
