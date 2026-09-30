import subprocess
from pathlib import Path

import pytest

from app.models.runtime import ProposedFileChange
from app.tools.filesystem import FileSystemTool
from app.tools.repo import RepoScanner
from app.tools.git_tools import GitTool


@pytest.mark.parametrize("path", [".env", ".env.production", "config/private.key", ".aws/credentials", "config/a.pem"])
def test_secret_paths_never_enter_context_or_preview(tmp_path: Path, path: str) -> None:
    secret = tmp_path / path
    secret.parent.mkdir(parents=True, exist_ok=True)
    secret.write_text("SECRET_SENTINEL")
    (tmp_path / "README.md").write_text("public")
    scanner = RepoScanner(tmp_path, 100_000)
    assert "SECRET_SENTINEL" not in str(scanner.focused_snapshot(path))
    assert path not in scanner.tree()
    with pytest.raises(PermissionError):
        FileSystemTool(tmp_path, 100_000).preview_change(ProposedFileChange(path=path, content="replace"))


@pytest.mark.parametrize("path", ["../escape.txt", ".git/config", "."])
def test_protected_paths_rejected(tmp_path: Path, path: str) -> None:
    with pytest.raises(ValueError):
        FileSystemTool(tmp_path, 100_000).apply_change(ProposedFileChange(path=path, content="bad"))


def test_gitignored_and_binary_files_are_not_prompt_content(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text("private.txt\n")
    (tmp_path / "private.txt").write_text("PRIVATE")
    (tmp_path / "binary.dat").write_bytes(b"\xff\x00")
    (tmp_path / "README.md").write_text("public")
    scanner = RepoScanner(tmp_path, 100_000)
    assert "private.txt" not in scanner.tree()
    assert "binary.dat" not in scanner.focused_snapshot("binary")


def test_staged_secret_diff_is_filtered(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / ".env.production").write_text("SECRET_SENTINEL")
    (tmp_path / "safe.txt").write_text("public")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    diff = GitTool(tmp_path).diff(staged=True)
    assert "SECRET_SENTINEL" not in diff
    assert "+public" in diff


def test_missing_content_cannot_erase_file(tmp_path: Path) -> None:
    (tmp_path / "safe.txt").write_text("keep")
    with pytest.raises(ValueError, match="Missing content"):
        FileSystemTool(tmp_path, 100_000).apply_change(ProposedFileChange(path="safe.txt"))
    assert (tmp_path / "safe.txt").read_text() == "keep"


def test_symlink_outside_workspace_is_not_read_or_written(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("PRIVATE")
    link = workspace / "link.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("Creating symlinks requires OS permission")
    assert "link.txt" not in RepoScanner(workspace, 100_000).focused_snapshot("link")
    with pytest.raises(ValueError, match="escapes workspace"):
        FileSystemTool(workspace, 100_000).apply_change(ProposedFileChange(path="link.txt", content="no"))
    assert outside.read_text() == "PRIVATE"
