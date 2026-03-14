from __future__ import annotations

import os
from pathlib import Path


IGNORED_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    "node_modules",
    "data",
}


class RepoScanner:
    """Builds focused repository context for agent prompts."""

    def __init__(self, root: Path, max_file_bytes: int) -> None:
        self.root = root
        self.max_file_bytes = max_file_bytes

    def all_files(self) -> list[Path]:
        files: list[Path] = []
        for current_root, dir_names, file_names in os.walk(self.root):
            dir_names[:] = [name for name in dir_names if name not in IGNORED_DIRS]
            for file_name in file_names:
                path = Path(current_root) / file_name
                if path.stat().st_size <= self.max_file_bytes:
                    files.append(path)
        return sorted(files)

    def tree(self, max_depth: int = 3) -> str:
        lines: list[str] = [self.root.name + "/"]
        root_parts = len(self.root.parts)
        for path in self.all_files():
            depth = len(path.parts) - root_parts
            if depth > max_depth:
                continue
            lines.append("  " * (depth - 1) + f"- {path.relative_to(self.root).as_posix()}")
        return "\n".join(lines[:120])

    def select_relevant_files(self, task: str, limit: int = 8) -> list[Path]:
        keywords = {part.lower() for part in task.replace("-", " ").replace("_", " ").split() if len(part) > 2}
        ranked: list[tuple[int, Path]] = []
        for path in self.all_files():
            rel = path.relative_to(self.root).as_posix().lower()
            score = sum(1 for keyword in keywords if keyword in rel)
            if path.name in {"README.md", "pyproject.toml"}:
                score += 1
            ranked.append((score, path))
        ranked.sort(key=lambda item: (-item[0], item[1].as_posix()))
        chosen = [path for score, path in ranked if score > 0][:limit]
        if not chosen:
            chosen = [path for _, path in ranked[:limit]]
        return chosen

    def focused_snapshot(self, task: str, limit: int = 8) -> dict[str, str]:
        snapshot: dict[str, str] = {}
        for path in self.select_relevant_files(task, limit=limit):
            snapshot[path.relative_to(self.root).as_posix()] = path.read_text(encoding="utf-8")[:12000]
        return snapshot

