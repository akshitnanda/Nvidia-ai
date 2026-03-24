# Contributing

Thanks for contributing to NVIDIA Local Dev Swarm.

## Local Setup

```powershell
powershell -ExecutionPolicy Bypass -File scripts/bootstrap.ps1
```

For docs work:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/docs.ps1
```

## Workflow

1. Create a branch for your change.
2. Keep changes small and reviewable.
3. Run the local checks before opening a pull request.
4. Update docs when behavior or setup changes.

## Checks

```powershell
python -m pytest -q
python -m compileall app tests
mkdocs build --strict
```

## Pull Requests

- explain the user-visible change
- mention any risks or follow-ups
- include screenshots or terminal output for UI/demo updates when helpful
- update `wiki/` starter pages if the public workflow story changes substantially

## Scope

This project favors:

- local-first developer workflows
- typed Python
- minimal, testable changes
- GitHub-friendly demoability
