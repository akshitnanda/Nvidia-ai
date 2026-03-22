# NVIDIA Local Dev Swarm

GitHub-friendly multi-agent developer workflow for local repos, with two modes that matter when you are showing the project publicly:

- `demo` mode for safe, deterministic walkthroughs without an NVIDIA API key
- live NVIDIA mode for real planning, implementation, review, and release-note generation

## What You Can Show In Under Five Minutes

1. Bootstrap the repo.
2. Run `swarm demo --mode plan`.
3. Open the local dashboard.
4. Point at the GitHub Actions badges and Pages docs once the repo is published.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/bootstrap.ps1
swarm demo --mode plan --task "Show how the local swarm works"
swarm dashboard
```

## Why The Demo Path Exists

The original repo already had a solid local architecture, but it still assumed a bit too much from a first-time GitHub visitor:

- an API key for meaningful behavior
- enough patience to read an architecture-heavy README before seeing something work
- confidence that CI and releases would be handled later

The current setup fixes that by making the safest path also the shortest path.

## Repo Highlights

- Typer CLI for `analyze-repo`, `plan`, `implement`, `review`, `release`, `watch-repo`, `dashboard`, and `demo`
- FastAPI dashboard with a browser-friendly landing page plus run-artifact endpoints
- config-driven agent/model routing under `config/`
- SQLite-backed memory and local run artifacts under `data/`
- GitHub Actions for CI, Pages deployment, and release packaging

## Best Entry Points

- Start with [Quickstart](quickstart.md) if you want a clean first run.
- Use [Demo Guide](demo.md) for screen-sharing or public showcases.
- Use [GitHub Ops](github.md) when wiring Pages, tags, and release assets in GitHub.
