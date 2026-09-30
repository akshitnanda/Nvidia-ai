from __future__ import annotations

import subprocess
from pathlib import Path

from app.tools.paths import excluded_path


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

    def diff(self, staged: bool = False, revision: str | None = None) -> str:
        if not self.is_repo():
            return "No git diff available because this is not a git repository."
        args = ["git", "--literal-pathspecs", "diff", "--no-ext-diff", "--no-textconv"]
        if staged:
            args.append("--staged")
        if revision:
            args.append(self.resolve_revision(revision) + "..HEAD")
        names = subprocess.run([*args, "--name-only", "-z"], cwd=self.root, capture_output=True, check=True)
        paths = [name for name in names.stdout.decode("utf-8", errors="replace").split("\0")
                 if name and not excluded_path(Path(name))]
        chunks = []
        # Bound each command line for Windows and each prompt for large repositories.
        for offset in range(0, len(paths), 50):
            result = subprocess.run([*args, "--", *paths[offset:offset + 50]], cwd=self.root,
                                    capture_output=True, text=True, encoding="utf-8", errors="replace", check=True)
            chunks.append(result.stdout)
            if sum(map(len, chunks)) >= 100_000:
                break
        return "".join(chunks)[:100_000].strip()

    def resolve_revision(self, revision: str) -> str:
        result = subprocess.run(["git", "rev-parse", "--verify", "--end-of-options", revision + "^{commit}"],
                                cwd=self.root, capture_output=True, text=True, check=True)
        return result.stdout.strip()

    def commits_since(self, revision: str) -> str:
        commit = self.resolve_revision(revision)
        return subprocess.run(["git", "log", commit + "..HEAD", "--oneline", "--decorate", "-50"],
                              cwd=self.root, capture_output=True, text=True, check=True).stdout.strip()

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

    def commit(self, message: str, paths: list[str]) -> str:
        if not self.is_repo():
            raise RuntimeError("Cannot commit outside a git repository.")
        staged = subprocess.run(["git", "diff", "--cached", "--name-only"], cwd=self.root,
                                capture_output=True, text=True, check=True)
        if staged.stdout.strip():
            raise RuntimeError("Refusing automatic commit while other changes are staged.")
        if not paths:
            raise ValueError("A commit requires explicitly selected files.")
        add_result = subprocess.run(
            ["git", "--literal-pathspecs", "add", "--", *paths],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=True,
        )
        commit_result = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=True,
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
