from __future__ import annotations

import subprocess
from pathlib import Path


class GitTool:
    """Thin wrapper around local git commands."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def is_repo(self) -> bool:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0

    def status(self) -> str:
        if not self.is_repo():
            return "Not a git repository."
        result = subprocess.run(
            ["git", "status", "--short"],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout.strip()

    def diff(self, staged: bool = False) -> str:
        if not self.is_repo():
            return "No git diff available because this is not a git repository."
        args = ["git", "diff"]
        if staged:
            args.append("--staged")
        result = subprocess.run(args, cwd=self.root, capture_output=True, text=True, check=False)
        return result.stdout.strip()

    def recent_commits(self, count: int = 5) -> str:
        if not self.is_repo():
            return "No git history available because this is not a git repository."
        result = subprocess.run(
            ["git", "log", f"-{count}", "--oneline", "--decorate"],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout.strip()

    def commit(self, message: str) -> str:
        if not self.is_repo():
            return "Skipping commit because this is not a git repository."
        add_result = subprocess.run(
            ["git", "add", "-A"],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=False,
        )
        commit_result = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=False,
        )
        return "\n".join(
            part
            for part in [
                add_result.stdout.strip(),
                add_result.stderr.strip(),
                commit_result.stdout.strip(),
                commit_result.stderr.strip(),
            ]
            if part
        )
