# NVIDIA Local Dev Swarm Wiki

NVIDIA Local Dev Swarm is a local-first multi-agent developer workflow for Python repositories, with:

- live NVIDIA-backed inference for real runs
- a deterministic `demo` mode for no-key walkthroughs
- a lightweight FastAPI dashboard
- GitHub Actions for CI, docs deployment, and release packaging

## Start Here

- Read the main README for the fastest overview.
- Use the wiki when you want slightly more operational detail.

## Recommended Pages

- [Quickstart](Quickstart)
- [Demo Workflow](Demo-Workflow)
- [Architecture Notes](Architecture-Notes)
- [Release Process](Release-Process)

## Useful Links

- Repository: `https://github.com/akshitnanda/Nvidia-ai`
- Docs site: `https://akshitnanda.github.io/Nvidia-ai/`
- Releases: `https://github.com/akshitnanda/Nvidia-ai/releases`
- Actions: `https://github.com/akshitnanda/Nvidia-ai/actions`

## Good First Demo

```powershell
powershell -ExecutionPolicy Bypass -File scripts/bootstrap.ps1
swarm demo --mode plan --task "Show how this repo works"
swarm dashboard
```
