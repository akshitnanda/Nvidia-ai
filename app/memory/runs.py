"""Bounded, read-only access to run artifacts for the CLI and dashboard."""

import json
import re
from pathlib import Path
from typing import Any

MAX_ARTIFACT_BYTES = 1_000_000


class RunStore:
    def __init__(self, data_dir: Path) -> None:
        self.runs_dir = (data_dir / "runs").resolve()

    def resolve(self, run_id: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", run_id):
            raise FileNotFoundError("Run not found")
        path = self.runs_dir / run_id
        if path.is_symlink() or not path.is_dir() or path.resolve().parent != self.runs_dir:
            raise FileNotFoundError("Run not found")
        return path

    def _read(self, path: Path) -> Any:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_ARTIFACT_BYTES:
            raise ValueError("Artifact unavailable or larger than 1 MB")
        text = path.read_text(encoding="utf-8")
        if path.suffix == ".json":
            return json.loads(text)
        if path.suffix == ".jsonl":
            rows = []
            for line in text.splitlines():
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue  # A writer may not have completed the last line yet.
            return rows
        return text

    def summary(self, run_id: str) -> dict[str, Any]:
        directory = self.resolve(run_id)
        summary: dict[str, Any] = {"run_id": run_id, "status": "unknown", "mode": "unknown"}
        try:
            manifest = self._read(directory / "run.json")
            if isinstance(manifest, dict):
                summary.update(manifest)
        except (OSError, ValueError, UnicodeError):
            pass
        summary["run_id"] = run_id
        try:
            usage = self._read(directory / "usage.jsonl")
            rows = [row for row in usage if isinstance(row, dict) and isinstance(row.get("usage"), dict)]
            summary["total_tokens"] = sum(max(0, int(row["usage"].get("total_tokens", 0))) for row in rows)
            summary["model_calls"] = len(rows)
        except (OSError, ValueError, TypeError, UnicodeError):
            summary.update(total_tokens=0, model_calls=0)
        return summary

    def list(self, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        if not self.runs_dir.exists():
            return []
        results = []
        for directory in sorted(self.runs_dir.iterdir(), reverse=True):
            try:
                self.resolve(directory.name)
            except (FileNotFoundError, OSError):
                continue
            if offset:
                offset -= 1
                continue
            results.append(self.summary(directory.name))
            if len(results) >= limit:
                break
        return results

    def get(self, run_id: str) -> dict[str, Any]:
        directory = self.resolve(run_id)
        artifacts: dict[str, Any] = {}
        errors: dict[str, str] = {}
        for path in sorted(directory.iterdir())[:100]:
            if path.suffix not in {".json", ".jsonl", ".md", ".txt", ".diff"}:
                continue
            try:
                artifacts[path.name] = self._read(path)
            except (OSError, ValueError, UnicodeError) as exc:
                errors[path.name] = f"Artifact could not be read ({type(exc).__name__})."
        return {"run_id": run_id, "summary": self.summary(run_id), "artifacts": artifacts, "artifact_errors": errors}
