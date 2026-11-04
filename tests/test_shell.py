import sys
from pathlib import Path

import psutil

from app.tools.shell import ShellTool


def test_timeout_stops_validation_and_its_child(tmp_path: Path) -> None:
    (tmp_path / "child.py").write_text("import os,time\nfrom pathlib import Path\nPath('child.pid').write_text(str(os.getpid()))\ntime.sleep(60)\n")
    (tmp_path / "parent.py").write_text("import subprocess,sys,time\nsubprocess.Popen([sys.executable,'child.py'])\ntime.sleep(60)\n")
    result = ShellTool(tmp_path).run(f'"{sys.executable}" parent.py', timeout_seconds=3)
    assert result.exit_code == 124
    assert "timed out" in result.stderr
    child = int((tmp_path / "child.pid").read_text())
    assert not psutil.pid_exists(child) or psutil.Process(child).status() == psutil.STATUS_ZOMBIE


def test_command_output_is_bounded_and_marked_failed(tmp_path: Path) -> None:
    (tmp_path / "output.py").write_text("print('x' * 100000)\n")
    result = ShellTool(tmp_path).run(f'"{sys.executable}" output.py', max_output_bytes=1000)
    assert result.exit_code == 125
    assert len(result.stdout) <= 1000
    assert "output limit" in result.stderr


def test_stdout_stderr_and_exit_status_are_preserved(tmp_path: Path) -> None:
    (tmp_path / "output.py").write_text("import sys\nprint('out')\nprint('err',file=sys.stderr)\nsys.exit(7)\n")
    result = ShellTool(tmp_path).run(f'"{sys.executable}" output.py')
    assert result.exit_code == 7
    assert result.stdout.strip() == "out"
    assert result.stderr.strip() == "err"
