"""Stop an owned subprocess and its observed descendants."""

import subprocess

import psutil


def stop_process_tree(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    try:
        parent = psutil.Process(process.pid)
        targets = parent.children(recursive=True) + [parent]
        for target in reversed(targets):
            try:
                target.kill()
            except psutil.NoSuchProcess:
                pass
        _, alive = psutil.wait_procs(targets, timeout=3)
        alive = [target for target in alive if target.is_running() and target.status() != psutil.STATUS_ZOMBIE]
        if alive:
            raise RuntimeError("A subprocess did not stop after cancellation.")
    except psutil.NoSuchProcess:
        pass
    process.wait(timeout=5)
