from __future__ import annotations

from pathlib import Path


class PromptLoader:
    def __init__(self, config_dir: Path) -> None:
        self.config_dir = config_dir

    def load(self, relative_path: str) -> str:
        return (self.config_dir / relative_path).read_text(encoding="utf-8")

