"""Shared exclusions for model context, file edits, and watch events."""

from pathlib import Path

IGNORED_DIRS = {
    ".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", "node_modules", "data", "dist", "build", "site",
}


def is_secret_path(path: str | Path) -> bool:
    parts = Path(path).parts
    for part in parts:
        name = part.lower()
        if name in {".ssh", ".aws", ".azure", ".gnupg", "credentials", "credentials.json"}:
            return True
        if name.startswith(".env") and name not in {".env.example", ".env.sample", ".env.template"}:
            return True
        if name.endswith((".pem", ".key", ".p12", ".pfx", ".bak")) or name.startswith("id_rsa"):
            return True
    return False


def excluded_path(path: Path) -> bool:
    return is_secret_path(path) or any(part.lower() in IGNORED_DIRS for part in path.parts)
