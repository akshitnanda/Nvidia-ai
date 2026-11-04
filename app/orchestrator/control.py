"""Shared cancellation checkpoints, per-run call limits, and durable approval."""

import hashlib
import time
from threading import RLock
from uuid import uuid4


class RunStopped(RuntimeError):
    status = "cancelled"


class BudgetExceeded(RunStopped):
    status = "budget_exceeded"


class RunInterrupted(RunStopped):
    status = "interrupted"


class RunControl:
    def __init__(self, max_calls=100, max_tokens=2_000_000, checkpoint=None) -> None:
        self.max_calls, self.max_tokens = max_calls, max_tokens
        self.calls = self.tokens = 0
        self._checkpoint = checkpoint
        self._lock = RLock()

    def check(self) -> None:
        if self._checkpoint:
            self._checkpoint()
        with self._lock:
            if self.tokens > self.max_tokens:
                raise BudgetExceeded(f"Reported token limit exceeded ({self.max_tokens}).")

    def before_call(self) -> None:
        self.check()
        with self._lock:
            if self.calls >= self.max_calls:
                raise BudgetExceeded(f"Model call limit reached ({self.max_calls}).")
            if self.tokens >= self.max_tokens:
                raise BudgetExceeded(f"Reported token limit reached ({self.max_tokens}).")
            self.calls += 1

    def record_tokens(self, tokens: int) -> None:
        with self._lock:
            self.tokens += max(0, tokens)


class JobControl(RunControl):
    def __init__(self, store, job_id: str, owner: str, logger, max_calls: int, max_tokens: int) -> None:
        self.store, self.job_id, self.owner, self.logger = store, job_id, owner, logger
        super().__init__(max_calls, max_tokens, self._owned)

    def _owned(self) -> None:
        if not self.store.owned(self.job_id, self.owner):
            if self.store.get(self.job_id)["state"] == "cancelling":
                raise RunStopped("Job cancelled by operator.")
            raise RunInterrupted("Scheduler ownership lost; retry starts a fresh run.")

    def approve(self, previews) -> bool:
        self.check()
        diff = "\n\n".join(preview.diff or f"{preview.action}: {preview.path}" for preview in previews)
        ticket = uuid4().hex
        approval = {"ticket": ticket, "diff": diff, "digest": hashlib.sha256(diff.encode()).hexdigest(),
                    "files": len(previews), "risky": any(preview.risky for preview in previews)}
        self.store.request_approval(self.job_id, approval)
        self.logger.manifest.update(status="awaiting_approval")
        self.logger.write_json("run.json", self.logger.manifest)
        self.logger.event("approval", "awaiting_approval", ticket=ticket, digest=approval["digest"])
        while True:
            self.check()
            decision = self.store.consume_decision(self.job_id)
            if decision is not None:
                self.logger.event("approval", "approved" if decision else "declined", ticket=ticket)
                self.logger.manifest.update(status="running")
                self.logger.write_json("run.json", self.logger.manifest)
                if not decision:
                    raise RunStopped("File application declined by operator.")
                return True
            time.sleep(.15)
