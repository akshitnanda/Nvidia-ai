from __future__ import annotations

import json
import logging
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


class RunLogger:
    """Stores run artifacts locally for later inspection."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.runs_dir = data_dir / "runs"
        self.usage_dir = data_dir / "usage"
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.usage_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        self.run_id = f"{stamp}-{uuid4().hex[:8]}"
        self.run_dir = self.runs_dir / self.run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self.manifest: dict[str, Any] = {}

    def start(self, mode: str, task: str, provider: str) -> None:
        if self.manifest:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            self.run_id = f"{stamp}-{uuid4().hex[:8]}"
            self.run_dir = self.runs_dir / self.run_id
            self.run_dir.mkdir(parents=True, exist_ok=False)
        self.manifest = {
            "run_id": self.run_id, "mode": mode, "task": task, "provider": provider,
            "status": "running", "started_at": datetime.now(timezone.utc).isoformat(),
        }
        self.write_json("run.json", self.manifest)

    def finish(self, result: Any = None, error: BaseException | None = None) -> None:
        if result is not None:
            self.write_json("result.json", result)
            self.manifest.update(status="succeeded" if result.success else "failed", summary=result.summary,
                                 changed_files=result.changed_files, validation_status=result.validation_status)
        else:
            self.manifest.update(status="failed", error=str(error), summary="Workflow failed; inspect run artifacts.")
        self.manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
        self.write_json("run.json", self.manifest)

    def event(self, agent: str, status: str, **details: Any) -> None:
        self._append(self.run_dir / "events.jsonl", {
            "at": datetime.now(timezone.utc).isoformat(), "agent": agent, "status": status, **details,
        })

    def _append(self, path: Path, payload: Any) -> None:
        with self._lock, path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(self._normalize(payload), ensure_ascii=False) + "\n")

    def _normalize(self, payload: Any) -> Any:
        if is_dataclass(payload):
            return asdict(payload)
        if hasattr(payload, "model_dump"):
            return payload.model_dump(mode="json")
        if isinstance(payload, Path):
            return str(payload)
        if isinstance(payload, dict):
            return {key: self._normalize(value) for key, value in payload.items()}
        if isinstance(payload, list):
            return [self._normalize(item) for item in payload]
        return payload

    def write_json(self, name: str, payload: Any) -> Path:
        path = self.run_dir / name
        with self._lock:
            temporary = path.with_name(path.name + ".tmp")
            temporary.write_text(json.dumps(self._normalize(payload), indent=2, ensure_ascii=False), encoding="utf-8")
            temporary.replace(path)
        return path

    def write_text(self, name: str, text: str) -> Path:
        path = self.run_dir / name
        path.write_text(text, encoding="utf-8")
        return path

    def append_usage(self, payload: dict[str, Any]) -> Path:
        path = self.usage_dir / "usage.jsonl"
        entry = {**payload, "run_id": self.run_id, "at": datetime.now(timezone.utc).isoformat()}
        self._append(path, entry)
        self._append(self.run_dir / "usage.jsonl", entry)
        return path

