from __future__ import annotations

import json

from app.models.runtime import CompletionRequest, CompletionResponse, ProviderUsage


class DemoProvider:
    """Deterministic local responses for GitHub demos and smoke testing."""

    model_name = "demo/local-scripted"

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        agent_name = str(request.metadata.get("agent") or request.profile_name)
        task = self._extract_task(request)
        content = self._render(agent_name, task)
        tokens = max(len(content.split()), 1)
        return CompletionResponse(
            model=self.model_name,
            content=content,
            usage=ProviderUsage(
                prompt_tokens=max(sum(len(message.content.split()) for message in request.messages), 1),
                completion_tokens=tokens,
                total_tokens=tokens,
            ),
            raw_response={"mode": "demo", "agent": agent_name, "task": task},
        )

    def _extract_task(self, request: CompletionRequest) -> str:
        for message in reversed(request.messages):
            if message.role != "user":
                continue
            if "\n\nAgent Role:\n" in message.content:
                return message.content.split("\n\nAgent Role:\n", 1)[0].replace("Task:\n", "", 1).strip()
            if message.content.strip():
                return message.content.strip()
        return "Explore the repository."

    def _render(self, agent_name: str, task: str) -> str:
        if agent_name == "planner":
            return self._planner(task)
        if agent_name == "coder":
            return self._changeset(
                "Demo mode returns a no-op code changeset so the repository stays clean during walkthroughs.",
                ["python -m compileall app tests"],
            )
        if agent_name == "tester":
            return self._changeset(
                "Demo mode keeps tests unchanged and suggests a lightweight verification command.",
                ["python -m pytest -q"],
            )
        if agent_name == "docs":
            return self._changeset(
                "Demo mode skips documentation edits and focuses on showing the orchestration flow safely.",
                [],
            )
        if agent_name == "reviewer":
            return self._review(task)
        if agent_name == "release":
            return self._release(task)
        return self._context(task)

    def _planner(self, task: str) -> str:
        return (
            "1. Objective\n"
            f"Show a safe scripted walkthrough for: {task}\n\n"
            "2. Recommended Steps\n"
            "- Inspect the repository summary and recent git state.\n"
            "- Generate a concise implementation plan.\n"
            "- Preview a no-op implementation response that keeps tracked files unchanged.\n"
            "- Run a lightweight validation command if the operator wants a smoke test.\n\n"
            "3. Risks\n"
            "- Demo mode uses deterministic local text, so it does not reflect live NVIDIA model quality.\n"
            "- Implementation previews intentionally avoid writing tracked files.\n\n"
            "4. Validation\n"
            "- Run `python -m pytest -q` after bootstrapping the environment.\n"
            "- Open the dashboard and confirm new run artifacts appear under `data/runs/`.\n\n"
            "5. Suggested Agent Handoffs\n"
            "- Coder: return a preview-only changeset.\n"
            "- Tester: suggest the repo smoke test command.\n"
            "- Reviewer: summarize residual demo-mode limitations.\n"
        )

    def _review(self, task: str) -> str:
        return (
            "1. Findings\n"
            "- No blocking issues were detected in demo mode.\n"
            "- The workflow stayed read-only, which is the expected GitHub-demo behavior.\n\n"
            "2. Residual Risks\n"
            "- Demo output is scripted, so it should not be used to evaluate production model behavior.\n"
            f"- Any live implementation for `{task}` still requires a configured NVIDIA endpoint.\n\n"
            "3. Recommended Next Steps\n"
            "- Switch `NVIDIA_PROVIDER_MODE` to `serverless` or `local_nim` for real model calls.\n"
            "- Re-run the same command outside demo mode when you are ready to make actual changes.\n"
        )

    def _release(self, task: str) -> str:
        return (
            "1. Release Summary\n"
            "Prepared a GitHub-friendly demo path with deterministic local responses.\n\n"
            "2. Highlights\n"
            "- Added a no-key walkthrough mode for CLI and dashboard demos.\n"
            f"- Preserved the live-provider path for real work on: {task}\n\n"
            "3. Validation Notes\n"
            "- Intended smoke test: `python -m pytest -q`\n"
            "- Intended UI check: `swarm dashboard` then open `/` and `/docs`\n\n"
            "4. Follow-ups\n"
            "- Capture screenshots or a terminal recording once the repo is published.\n"
        )

    def _context(self, task: str) -> str:
        return (
            "1. Repo Snapshot\n"
            "- Python project with a Typer CLI in `app/cli/app.py`.\n"
            "- Optional FastAPI dashboard in `app/api/dashboard.py`.\n"
            "- Config-driven agents, models, and prompts under `config/`.\n\n"
            "2. Standards\n"
            "- Typed Python modules and small, focused helpers.\n"
            "- Preview-first filesystem changes and local artifact logging.\n"
            "- Tests cover config loading, memory storage, and patch previews.\n\n"
            "3. Recent Decisions\n"
            f"- Current demo task: {task}\n"
            "- Favor a clean first-run experience from a GitHub checkout.\n\n"
            "4. Open Questions\n"
            "- Which NVIDIA-hosted model mix should be the default for live demos?\n"
            "- Should future demos apply sample changes under a dedicated sandbox folder?\n"
        )

    def _changeset(self, summary: str, commands: list[str]) -> str:
        payload = {
            "summary": summary,
            "changes": [],
            "commands": commands,
        }
        return "```json\n" + json.dumps(payload, indent=2) + "\n```"
