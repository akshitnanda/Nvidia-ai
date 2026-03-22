# Quickstart

## Windows

```powershell
powershell -ExecutionPolicy Bypass -File scripts/bootstrap.ps1
swarm demo
swarm dashboard
```

Open `http://127.0.0.1:8787/` after the dashboard starts.

## Cross-platform

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m app.cli.app demo
python -m app.cli.app dashboard
```

On Windows PowerShell, activate with:

```powershell
.venv\Scripts\Activate.ps1
```

## Live NVIDIA Mode

When you are ready to move past the scripted walkthrough:

1. Copy `.env.example` to `.env`.
2. Set `NVIDIA_API_KEY`.
3. Keep `NVIDIA_PROVIDER_MODE=serverless`, or change it to `local_nim` if you are pointing at a compatible local endpoint.

Example:

```powershell
swarm plan "Add a FastAPI health endpoint and tests"
swarm implement "Add a FastAPI health endpoint and tests" --apply
swarm review
```

## Local Validation

```powershell
python -m pytest -q
python -m compileall app tests
```

If you want to preview the docs site locally:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/docs.ps1
```
