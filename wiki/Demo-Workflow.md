# Demo Workflow

## Why Demo Mode Exists

Demo mode is for:

- GitHub visitors
- screen-shares
- onboarding
- quick walkthroughs without secrets

It returns deterministic local responses while still exercising the CLI flow and writing normal run artifacts under `data/runs/`.

## Best Commands For A Walkthrough

```powershell
swarm demo --mode analyze
swarm demo --mode plan --task "Show how the local swarm works"
swarm demo --mode implement --task "Preview how a code change would flow"
swarm dashboard
```

## What To Emphasize

- The CLI is real.
- The dashboard is real.
- The GitHub automation is real.
- The model output is scripted on purpose so anyone can try the project safely.

## Replacing The README Placeholders

The repository currently uses placeholder images for:

- CLI demo
- dashboard preview

Replace them with:

1. a real terminal screenshot or short GIF from `swarm demo --mode plan`
2. a browser screenshot of the dashboard home page

See `docs/assets/README.md` in the main repository for a quick capture checklist.
