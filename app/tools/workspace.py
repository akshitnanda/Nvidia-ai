"""Create retained Git worktrees for implementation runs."""

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class IsolatedWorkspace:
    path: Path
    branch: str
    base_commit: str

    @classmethod
    def create(cls, root: Path, data_dir: Path, run_id: str) -> "IsolatedWorkspace":
        def git(*args: str) -> str:
            return subprocess.run(
                ["git", *args], cwd=root, capture_output=True, text=True,
                encoding="utf-8", errors="replace", check=True,
            ).stdout.strip()

        if Path(git("rev-parse", "--show-toplevel")).resolve() != root.resolve():
            raise ValueError("Isolated implementation requires the Git repository root.")
        base_commit = git("rev-parse", "--verify", "HEAD^{commit}")
        parent = (data_dir / "workspaces").resolve()
        parent.mkdir(parents=True, exist_ok=True)
        path = parent / run_id
        if path.exists():
            raise FileExistsError(f"Workspace already exists: {path}")
        branch = f"swarm/{run_id}"
        git("worktree", "add", "-b", branch, "--", str(path), base_commit)
        return cls(path, branch, base_commit)
