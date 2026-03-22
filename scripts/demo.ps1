param(
    [ValidateSet("analyze", "plan", "implement", "review", "release")]
    [string]$Mode = "analyze",
    [string]$Task = "Show how this project works from a fresh GitHub checkout.",
    [switch]$Dashboard
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    throw "Virtual environment not found. Run scripts/bootstrap.ps1 first."
}

. .\.venv\Scripts\Activate.ps1

if ($Dashboard) {
    swarm dashboard --root .
    exit
}

swarm demo --mode $Mode --task $Task --root .
