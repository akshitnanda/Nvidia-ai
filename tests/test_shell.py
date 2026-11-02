import subprocess
from pathlib import Path

import pytest

from app.tools.shell import ShellTool


def test_timeout_becomes_failed_validation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("test", 1, output=b"partial", stderr=b"details")
    monkeypatch.setattr(subprocess, "run", timeout)
    result = ShellTool(tmp_path).run("test", timeout_seconds=1)
    assert result.exit_code == 124
    assert result.stdout == "partial"
    assert "timed out" in result.stderr
