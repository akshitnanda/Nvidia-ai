from __future__ import annotations

import shutil
from pathlib import Path
from uuid import uuid4

from app.models.runtime import ProposedFileChange
from app.tools.paths import is_secret_path
from app.utils.patches import PreviewChange, build_unified_diff


class FileSystemTool:
    """Safe local file access with preview-first writes."""

    def __init__(self, root: Path, max_file_bytes: int) -> None:
        self.root = root.resolve()
        self.max_file_bytes = max_file_bytes

    def resolve(self, relative_path: str) -> Path:
        path = (self.root / relative_path).resolve()
        if self.root.resolve() not in path.parents and path != self.root.resolve():
            raise ValueError(f"Path escapes workspace: {relative_path}")
        relative = path.relative_to(self.root)
        if not relative.parts or any(part.lower() == ".git" for part in relative.parts):
            raise ValueError(f"Protected workspace path: {relative_path}")
        if is_secret_path(relative_path) or is_secret_path(relative):
            raise PermissionError(f"Refusing secret-like path: {relative_path}")
        if path.exists() and not path.is_file():
            raise ValueError(f"Not a regular file: {relative_path}")
        return path

    def read_text(self, relative_path: str) -> str:
        path = self.resolve(relative_path)
        if path.stat().st_size > self.max_file_bytes:
            raise ValueError(f"File too large to read safely: {relative_path}")
        return path.read_text(encoding="utf-8")

    def is_secret_path(self, relative_path: str) -> bool:
        return is_secret_path(relative_path)

    def preview_change(self, change: ProposedFileChange) -> PreviewChange:
        path = self.resolve(change.path)
        before = self.read_text(change.path) if path.exists() else ""
        if change.action == "create_or_update" and change.content is None:
            raise ValueError(f"Missing content for file change: {change.path}")
        if len((change.content or "").encode("utf-8")) > self.max_file_bytes:
            raise ValueError(f"Proposed file too large: {change.path}")
        after = "" if change.action == "delete" else (change.content or "")
        risky = self.is_secret_path(change.path) or change.action == "delete"
        return PreviewChange(
            path=path,
            action=change.action,
            diff=build_unified_diff(path.relative_to(self.root), before, after),
            risky=risky,
        )

    def apply_change(self, change: ProposedFileChange) -> Path:
        self.preview_change(change)
        if self.is_secret_path(change.path):
            raise PermissionError(f"Refusing to overwrite secret-like path: {change.path}")

        path = self.resolve(change.path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            backup = path.with_name(f"{path.name}.{uuid4().hex}.bak")
            shutil.copy2(path, backup)

        if change.action == "delete":
            if path.exists():
                path.unlink()
        else:
            path.write_text(change.content or "", encoding="utf-8")
        return path

