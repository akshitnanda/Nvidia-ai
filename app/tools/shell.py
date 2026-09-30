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
        try:
            completed = subprocess.run(
                command, cwd=self.root, shell=True, capture_output=True,
                text=True, encoding="utf-8", errors="replace",
                timeout=timeout_seconds, check=False,
            )
        except subprocess.TimeoutExpired as exc:
            def decode(value: str | bytes | None) -> str:
                return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value or ""
            return CommandExecution(
                command=command, exit_code=124, stdout=decode(exc.stdout),
                stderr=decode(exc.stderr) + f"\nCommand timed out after {timeout_seconds}s.",
                duration_seconds=round(time.perf_counter() - started, 3),
            )
        except OSError as exc:
            return CommandExecution(command=command, exit_code=127, stderr=str(exc),
                                    duration_seconds=round(time.perf_counter() - started, 3))
        duration = time.perf_counter() - started
        return CommandExecution(
            command=command,
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            duration_seconds=round(duration, 3),
        )

