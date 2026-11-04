"""A queue worker handles exactly one workflow and never auto-commits."""

import argparse
import os
import shlex
import subprocess
import sys
from pathlib import Path

from app.memory.jobs import JobStore
from app.models.jobs import JobRequest
from app.models.settings import Settings
from app.orchestrator.control import BudgetExceeded, JobControl, RunStopped
from app.orchestrator.engine import Orchestrator


def run(root: Path) -> int:
    settings = Settings()
    data_dir = (root / settings.swarm_data_dir).resolve()
    store = JobStore(data_dir, root)
    job_id, owner = os.environ["SWARM_JOB_ID"], os.environ["SWARM_JOB_OWNER"]
    engine = None
    try:
        request = JobRequest.model_validate(store.get(job_id)["request"])
        settings = settings.model_copy(update={"nvidia_provider_mode": "demo" if request.provider == "demo" else settings.nvidia_provider_mode,
                                               "swarm_auto_apply": False, "swarm_demo_scenario": request.scenario})
        if request.scenario == "repair_demo":
            args = [sys.executable, "-m", "py_compile", "swarm_demo_example.py"]
            command = subprocess.list2cmdline(args) if os.name == "nt" else shlex.join(args)
            settings = settings.model_copy(update={"swarm_default_test_command": command, "swarm_default_lint_command": ""})
        engine = Orchestrator(root, settings)
        store.attach(job_id, owner, engine.run_logger.run_id)
        engine.run_logger.control = control = JobControl(store, job_id, owner, engine.run_logger,
                                                         request.max_model_calls, request.max_total_tokens)
        control.check()
        if request.mode.value == "implement":
            result = engine.implement(request.task, apply_changes=request.apply_changes, run_validation=True,
                                      isolated=request.apply_changes, max_repairs=request.max_repairs)
        elif request.mode.value == "plan":
            result = engine.plan(request.task)
        elif request.mode.value == "analyze":
            result = engine.analyze_repo(task=request.task)
        elif request.mode.value == "review":
            result = engine.review(task=request.task)
        else:
            result = engine.release(task=request.task)
        control.check()
        if control.tokens > control.max_tokens:
            raise BudgetExceeded("Reported token limit exceeded by the final response.")
        store.finish(job_id, "succeeded" if result.success else "failed")
        return 0 if result.success else 1
    except RunStopped as exc:
        if engine is not None:
            engine.run_logger.finish(error=exc)
        store.finish(job_id, exc.status, str(exc))
        return 2
    except Exception as exc:
        if engine is not None:
            engine.run_logger.finish(error=exc)
        store.finish(job_id, "failed", str(exc))
        return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    raise SystemExit(run(parser.parse_args().root.resolve()))
