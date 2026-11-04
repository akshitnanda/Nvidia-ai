from __future__ import annotations

import os
import subprocess
import tempfile
import time
from pathlib import Path

from app.models.runtime import CommandExecution
from app.tools.processes import stop_process_tree


class ShellTool:
    """Configured validation with bounded output and descendant cleanup on timeout."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def run(self, command: str, timeout_seconds: float = 120, max_output_bytes: int = 1_000_000) -> CommandExecution:
        started = time.perf_counter()
        reason, exit_code = "", 127
        with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
            process = None
            try:
                process = subprocess.Popen(command, cwd=self.root, shell=True, stdout=stdout, stderr=stderr,
                                           creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                while True:
                    if time.perf_counter() - started >= timeout_seconds:
                        reason, exit_code = f"Command timed out after {timeout_seconds}s.", 124
                        stop_process_tree(process)
                        break
                    if os.fstat(stdout.fileno()).st_size + os.fstat(stderr.fileno()).st_size > max_output_bytes:
                        reason, exit_code = "Command output limit exceeded.", 125
                        stop_process_tree(process)
                        break
                    try:
                        exit_code = process.wait(timeout=.05)
                        break
                    except subprocess.TimeoutExpired:
                        continue
                if os.fstat(stdout.fileno()).st_size + os.fstat(stderr.fileno()).st_size > max_output_bytes:
                    reason, exit_code = "Command output limit exceeded.", 125
            except OSError as exc:
                reason = str(exc)
            finally:
                if process is not None and process.poll() is None:
                    stop_process_tree(process)
            stdout.seek(0)
            stderr.seek(0)
            out = stdout.read(max_output_bytes).decode("utf-8", errors="replace")
            err = stderr.read(max_output_bytes).decode("utf-8", errors="replace")
        return CommandExecution(command=command, exit_code=exit_code, stdout=out,
                                stderr=err + ("\n" + reason if reason else ""),
                                duration_seconds=round(time.perf_counter() - started, 3))
