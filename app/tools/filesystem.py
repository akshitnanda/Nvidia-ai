from __future__ import annotations

import shutil
from pathlib import Path

from app.models.runtime import ProposedFileChange
from app.utils.patches import PreviewChange, build_unified_diff


class FileSystemTool:
    """Safe local file access with preview-first writes."""

    def __init__(self, root: Path, max_file_bytes: int) -> None:
        self.root = root
        self.max_file_bytes = max_file_bytes

    def resolve(self, relative_path: str) -> Path:
        path = (self.root / relative_path).resolve()
        if self.root.resolve() not in path.parents and path != self.root.resolve():
            raise ValueError(f"Path escapes workspace: {relative_path}")
        return path

    def read_text(self, relative_path: str) -> str:
        path = self.resolve(relative_path)
        if path.stat().st_size > self.max_file_bytes:
            raise ValueError(f"File too large to read safely: {relative_path}")
        return path.read_text(encoding="utf-8")

    def is_secret_path(self, relative_path: str) -> bool:
        name = Path(relative_path).name.lower()
        return name == ".env" or name.endswith((".pem", ".key", ".p12"))

    def preview_change(self, change: ProposedFileChange) -> PreviewChange:
        path = self.resolve(change.path)
        before = path.read_text(encoding="utf-8") if path.exists() else ""
        after = "" if change.action == "delete" else (change.content or "")
        risky = self.is_secret_path(change.path) or change.action == "delete"
        return PreviewChange(
            path=path,
            action=change.action,
            diff=build_unified_diff(path.relative_to(self.root), before, after),
            risky=risky,
        )

    def apply_change(self, change: ProposedFileChange) -> Path:
        if self.is_secret_path(change.path):
            raise PermissionError(f"Refusing to overwrite secret-like path: {change.path}")

        path = self.resolve(change.path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            backup = path.with_suffix(path.suffix + ".bak")
            shutil.copy2(path, backup)

        if change.action == "delete":
            if path.exists():
                path.unlink()
        else:
            path.write_text(change.content or "", encoding="utf-8")
        return path

