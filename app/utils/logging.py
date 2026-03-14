from __future__ import annotations

import json
import logging
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
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

    def _normalize(self, payload: Any) -> Any:
        if is_dataclass(payload):
            return asdict(payload)
        if hasattr(payload, "model_dump"):
            return payload.model_dump()
        if isinstance(payload, Path):
            return str(payload)
        if isinstance(payload, dict):
            return {key: self._normalize(value) for key, value in payload.items()}
        if isinstance(payload, list):
            return [self._normalize(item) for item in payload]
        return payload

    def write_json(self, name: str, payload: Any) -> Path:
        path = self.run_dir / name
        with path.open("w", encoding="utf-8") as handle:
            json.dump(self._normalize(payload), handle, indent=2, ensure_ascii=False)
        return path

    def write_text(self, name: str, text: str) -> Path:
        path = self.run_dir / name
        path.write_text(text, encoding="utf-8")
        return path

    def append_usage(self, payload: dict[str, Any]) -> Path:
        path = self.usage_dir / "usage.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(self._normalize(payload), ensure_ascii=False) + "\n")
        return path

