# Demo Guide

## Safest Commands For A Public Walkthrough

```powershell
swarm demo --mode analyze
swarm demo --mode plan --task "Show how this repo works"
swarm demo --mode implement --task "Preview how a code change would flow"
swarm dashboard
```

## What Demo Mode Does

- returns deterministic local responses from a scripted provider
- avoids live NVIDIA API calls
- writes normal run artifacts to `data/runs/`
- keeps implementation demos preview-only unless you intentionally switch modes

## What To Say While Demoing

- The CLI and dashboard are real.
- The run artifacts are real.
- The provider path is swappable.
- The demo output is intentionally scripted so the repo is easy to try from GitHub without secrets.

## When To Leave Demo Mode

Use live mode if you want to evaluate actual model behavior, compare NVIDIA-served models, or apply generated changes to the repo.
