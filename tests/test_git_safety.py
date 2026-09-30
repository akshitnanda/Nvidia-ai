import subprocess
from pathlib import Path

import pytest

from app.tools.git_tools import GitTool


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout.strip()


def initialize(root: Path) -> GitTool:
    git(root, "init", "-q")
    git(root, "config", "user.name", "Test User")
    git(root, "config", "user.email", "test@example.invalid")
    git(root, "-c", "commit.gpgsign=false", "commit", "--allow-empty", "-m", "Initial")
    git(root, "config", "commit.gpgsign", "false")
    return GitTool(root)


def test_commit_does_not_stage_unrelated_files(tmp_path: Path) -> None:
    tool = initialize(tmp_path)
    (tmp_path / "chosen.txt").write_text("chosen")
    (tmp_path / "unrelated.txt").write_text("unrelated")
    tool.commit("Scoped change", ["chosen.txt"])
    assert git(tmp_path, "show", "--pretty=format:", "--name-only", "HEAD") == "chosen.txt"
    assert "?? unrelated.txt" in tool.status()


def test_commit_refuses_existing_staging(tmp_path: Path) -> None:
    tool = initialize(tmp_path)
    (tmp_path / "staged.txt").write_text("user work")
    (tmp_path / "chosen.txt").write_text("chosen")
    git(tmp_path, "add", "staged.txt")
    with pytest.raises(RuntimeError, match="other changes are staged"):
        tool.commit("Scoped", ["chosen.txt"])
    assert git(tmp_path, "diff", "--cached", "--name-only") == "staged.txt"


def test_revision_is_resolved_as_data(tmp_path: Path) -> None:
    tool = initialize(tmp_path)
    assert tool.diff(revision="HEAD") == ""
    with pytest.raises(subprocess.CalledProcessError):
        tool.diff(revision="HEAD; echo injected")


def test_commit_treats_glob_characters_in_filename_literally(tmp_path: Path) -> None:
    tool = initialize(tmp_path)
    (tmp_path / "[ab].txt").write_text("chosen")
    (tmp_path / "a.txt").write_text("unrelated")
    tool.commit("Literal path", ["[ab].txt"])
    assert git(tmp_path, "show", "--pretty=format:", "--name-only", "HEAD") == "[ab].txt"
    assert "?? a.txt" in tool.status()
