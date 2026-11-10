"""One local supervisor per data directory; workflows run in child processes."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from threading import Event, Thread
from uuid import uuid4

from app.memory.jobs import JobStore, TERMINAL
from app.models.jobs import JobRequest
from app.models.settings import Settings, resolve_config_dir
from app.tools.processes import stop_process_tree


class SchedulerLock:
    def __init__(self, path: Path) -> None:
        self.path, self.handle = path, None

    def acquire(self) -> None:
        if self.handle is not None:
            raise RuntimeError("Scheduler lock is already held.")
        self.handle = self.path.open("a+b")
        try:
            self.handle.seek(0)
            if not self.handle.read(1):
                self.handle.write(b"0")
                self.handle.flush()
            self.handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.handle.close()
            self.handle = None
            raise RuntimeError("Another dashboard owns this data directory's job queue.") from None

    def release(self) -> None:
        if self.handle:
            self.handle.close()
            self.handle = None


class JobManager:
    def __init__(self, root: Path, settings: Settings) -> None:
        self.root, self.settings = root.resolve(), settings
        if not self.root.is_dir():
            raise ValueError("Workspace root must be an existing directory.")
        self.data_dir = (self.root / settings.swarm_data_dir).resolve()
        self.store = JobStore(self.data_dir, self.root)
        self.owner = uuid4().hex
        self.lock = SchedulerLock(self.data_dir / "scheduler.lock")
        self.stop_event = Event()
        self.thread: Thread | None = None
        self.active: dict[str, tuple[subprocess.Popen, float, int, object]] = {}
        self.error: str | None = None
        self.last_heartbeat = 0.0

    def start(self) -> None:
        self.lock.acquire()
        try:
            for job in self.store.recover():
                self._mark_run(job, "interrupted", "Scheduler stopped before workflow completion.")
            self.store.heartbeat(self.owner)
            self.thread = Thread(target=self._loop, name="swarm-supervisor", daemon=True)
            self.thread.start()
        except BaseException:
            self.lock.release()
            raise

    def validate(self, request: JobRequest) -> None:
        if request.apply_changes:
            try:
                top = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=self.root, capture_output=True, text=True, check=True).stdout.strip()
                subprocess.run(["git", "rev-parse", "--verify", "HEAD^{commit}"], cwd=self.root, capture_output=True, check=True)
            except (OSError, subprocess.CalledProcessError):
                raise ValueError("Applying changes requires a committed Git repository root.") from None
            if Path(top).resolve() != self.root:
                raise ValueError("Start the dashboard at the Git repository root to apply changes.")
        if request.max_seconds > self.settings.swarm_job_max_seconds:
            raise ValueError(f"Runtime exceeds operator limit ({self.settings.swarm_job_max_seconds}s).")
        if request.max_model_calls > self.settings.swarm_job_max_calls:
            raise ValueError(f"Model calls exceed operator limit ({self.settings.swarm_job_max_calls}).")
        if request.max_total_tokens > self.settings.swarm_job_max_tokens:
            raise ValueError(f"Tokens exceed operator limit ({self.settings.swarm_job_max_tokens}).")
        if request.provider == "configured" and self.settings.nvidia_provider_mode == "serverless" and not self.settings.nvidia_api_key:
            raise ValueError("Configure NVIDIA_API_KEY before starting live workflows.")

    def submit(self, request: JobRequest, retry_of: str | None = None):
        self.validate(request)
        return self.store.submit(request, retry_of)

    def retry(self, job_id: str):
        previous = self.store.get(job_id)
        if previous["state"] not in TERMINAL:
            raise ValueError("Only terminal jobs can be retried.")
        return self.submit(JobRequest.model_validate(previous["request"]), retry_of=job_id)

    def _launch(self, job) -> None:
        env = os.environ.copy()
        # Configuration, including credentials, goes only to child environment, never the queue or argv.
        for name, field in Settings.model_fields.items():
            value = getattr(self.settings, name)
            if value is not None:
                env[field.alias or name] = str(value)
        env["SWARM_DATA_DIR"] = str(self.data_dir)
        env["SWARM_CONFIG_DIR"] = str(resolve_config_dir(self.root, self.settings.swarm_config_dir))
        env["SWARM_JOB_ID"], env["SWARM_JOB_OWNER"] = job["id"], self.owner
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        logs = self.data_dir / "jobs"
        logs.mkdir(exist_ok=True)
        handle = (logs / f"{job['id']}.log").open("wb")
        try:
            process = subprocess.Popen([sys.executable, "-m", "app.orchestrator.worker", "--root", str(self.root)],
                                       cwd=self.root, env=env, stdout=handle, stderr=subprocess.STDOUT,
                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                                       start_new_session=os.name != "nt")
        except BaseException:
            handle.close()
            raise
        self.active[job["id"]] = (process, time.monotonic(), job["request"]["max_seconds"], handle)

    def _mark_run(self, job, status: str, reason: str) -> None:
        if not job.get("run_id"):
            return
        from app.memory.runs import RunStore
        try:
            directory = RunStore(self.data_dir).resolve(job["run_id"])
            path = directory / "run.json"
            if path.exists():
                manifest = json.loads(path.read_text(encoding="utf-8"))
            else:
                manifest = {"run_id": job["run_id"], "task": job["request"]["task"],
                            "mode": job["request"]["mode"], "provider": job["request"]["provider"]}
            from app.memory.jobs import now
            manifest.update(status=status, error=reason, finished_at=now())
            temporary = directory / "supervisor-run.json.tmp"
            temporary.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            temporary.replace(path)
        except (OSError, ValueError):
            pass

    def _stop(self, job_id: str, status: str, reason: str) -> None:
        process, _, _, handle = self.active[job_id]
        stop_process_tree(process)
        handle.close()
        actual = self.store.finish(job_id, status, reason)
        if actual == status:
            self._mark_run(self.store.get(job_id), status, reason)
        del self.active[job_id]

    def _tick(self) -> None:
        if time.monotonic() - self.last_heartbeat >= 1:
            self.store.heartbeat(self.owner)
            self.last_heartbeat = time.monotonic()
        for job_id, (process, started, seconds, handle) in list(self.active.items()):
            job = self.store.get(job_id)
            if job["state"] in TERMINAL:
                stop_process_tree(process)
                handle.close()
                del self.active[job_id]
            elif job["state"] == "cancelling":
                self._stop(job_id, "cancelled", "Cancelled by operator.")
            elif time.monotonic() - started >= seconds:
                self._stop(job_id, "budget_exceeded", f"Runtime limit reached ({seconds}s, including approval wait).")
            elif process.poll() is not None:
                handle.close()
                if job["state"] in {"running", "awaiting_approval"}:
                    self.store.finish(job_id, "interrupted", "Worker exited without a terminal result; inspect retained artifacts.")
                    self._mark_run(job, "interrupted", "Worker exited without a terminal result.")
                del self.active[job_id]
        while len(self.active) < self.settings.swarm_job_concurrency:
            job = self.store.claim(self.owner)
            if job is None:
                break
            try:
                self.validate(JobRequest.model_validate(job["request"]))
                self._launch(job)
            except Exception as exc:
                self.store.finish(job["id"], "failed", str(exc))

    def _loop(self) -> None:
        try:
            while not self.stop_event.is_set():
                self._tick()
                self.stop_event.wait(.2)
        except Exception as exc:
            self.error = str(exc)
        finally:
            for job_id in list(self.active):
                try:
                    self._stop(job_id, "interrupted", "Dashboard supervisor stopped; retry starts a fresh run.")
                except Exception as exc:
                    self.error = str(exc)

    def close(self) -> None:
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=35)
            if self.thread.is_alive():
                raise RuntimeError("Supervisor is still stopping workers.")
        self.lock.release()
