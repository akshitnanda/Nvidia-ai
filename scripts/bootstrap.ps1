$ErrorActionPreference = "Stop"

if (-not (Test-Path ".venv")) {
    python -m venv .venv
}

. .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e .[dev]

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
}

Write-Host "Bootstrap complete. For a no-key walkthrough set NVIDIA_PROVIDER_MODE=demo, or set NVIDIA_API_KEY for live NVIDIA calls."
