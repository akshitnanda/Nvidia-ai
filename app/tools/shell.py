from __future__ import annotations

import subprocess
import time
from pathlib import Path

from app.models.runtime import CommandExecution


class ShellTool:
    """Runs local validation commands."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def run(self, command: str, timeout_seconds: int = 120) -> CommandExecution:
        started = time.perf_counter()
        completed = subprocess.run(
            command,
            cwd=self.root,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        duration = time.perf_counter() - started
        return CommandExecution(
            command=command,
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            duration_seconds=round(duration, 3),
        )

