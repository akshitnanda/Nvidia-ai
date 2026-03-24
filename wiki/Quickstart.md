# Quickstart

## Windows PowerShell

```powershell
powershell -ExecutionPolicy Bypass -File scripts/bootstrap.ps1
swarm demo
swarm dashboard
```

Then open `http://127.0.0.1:8787/`.

## Cross-platform Python

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m app.cli.app demo
python -m app.cli.app dashboard
```

## Live Mode

To use live NVIDIA inference instead of the scripted demo path:

1. Copy `.env.example` to `.env`.
2. Set `NVIDIA_API_KEY`.
3. Keep `NVIDIA_PROVIDER_MODE=serverless`, or switch to `local_nim` for a compatible local endpoint.

## Local Checks

```powershell
python -m pytest -q
python -m compileall app tests
mkdocs build --strict
```
