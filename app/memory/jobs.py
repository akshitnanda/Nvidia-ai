"""Durable queue transitions, approvals, and ownership in SQLite."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.models.jobs import JobRequest

ACTIVE = {"running", "awaiting_approval", "cancelling"}
TERMINAL = {"succeeded", "failed", "cancelled", "interrupted", "budget_exceeded"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobStore:
    def __init__(self, data_dir: Path, root: Path | None = None) -> None:
        self.data_dir = data_dir.resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.data_dir / "jobs.sqlite3"
        with self.connect() as conn:
            conn.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    state TEXT NOT NULL, request TEXT NOT NULL, retry_of TEXT,
                    owner TEXT, run_id TEXT, error TEXT, approval TEXT,
                    decision INTEGER, started_at TEXT, finished_at TEXT
                );
                CREATE TABLE IF NOT EXISTS scheduler (id INTEGER PRIMARY KEY CHECK(id=1),
                    owner TEXT, heartbeat REAL);
                CREATE TABLE IF NOT EXISTS workspace (id INTEGER PRIMARY KEY CHECK(id=1), root TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS jobs_queue ON jobs(state,created_at);
            """)
            if root is not None:
                conn.execute("BEGIN IMMEDIATE")
                bound = conn.execute("SELECT root FROM workspace WHERE id=1").fetchone()
                if bound and Path(bound["root"]).resolve() != root.resolve():
                    raise ValueError("This job queue belongs to another workspace; choose a different SWARM_DATA_DIR.")
                conn.execute("INSERT OR IGNORE INTO workspace VALUES(1,?)", (str(root.resolve()),))

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _decode(self, row: sqlite3.Row) -> dict[str, Any]:
        payload = dict(row)
        payload["request"] = json.loads(payload["request"])
        payload["approval"] = json.loads(payload["approval"]) if payload["approval"] else None
        # Decisions are internal; a consumed approval cannot be reused.
        payload["decision_pending"] = payload.pop("decision", None) is not None
        payload.pop("owner", None)
        return payload

    def get(self, job_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise FileNotFoundError("Job not found")
        return self._decode(row)

    def list(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM jobs ORDER BY CASE state WHEN 'awaiting_approval' THEN 0 "
                                "WHEN 'running' THEN 1 WHEN 'cancelling' THEN 2 WHEN 'queued' THEN 3 ELSE 4 END, "
                                "created_at DESC LIMIT ?", (limit,)).fetchall()
        return [self._decode(row) for row in rows]

    def submit(self, request: JobRequest, retry_of: str | None = None) -> dict[str, Any]:
        job_id, stamp = "job-" + uuid4().hex, now()
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            count = conn.execute("SELECT count(*) FROM jobs WHERE state='queued'").fetchone()[0]
            if count >= 64:
                raise ValueError("Queue is full (64 pending jobs).")
            conn.execute("INSERT INTO jobs(id,created_at,updated_at,state,request,retry_of) VALUES(?,?,?,'queued',?,?)",
                         (job_id, stamp, stamp, request.model_dump_json(), retry_of))
        return self.get(job_id)

    def retry(self, job_id: str) -> dict[str, Any]:
        previous = self.get(job_id)
        if previous["state"] not in TERMINAL:
            raise ValueError("Only terminal jobs can be retried.")
        return self.submit(JobRequest.model_validate(previous["request"]), retry_of=job_id)

    def claim(self, owner: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT id FROM jobs WHERE state='queued' ORDER BY created_at LIMIT 1").fetchone()
            if row is None:
                return None
            stamp = now()
            conn.execute("UPDATE jobs SET state='running',owner=?,started_at=?,updated_at=? WHERE id=?",
                         (owner, stamp, stamp, row["id"]))
        return self.get(row["id"])

    def cancel(self, job_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            conn.execute("UPDATE jobs SET state=CASE WHEN state='queued' THEN 'cancelled' ELSE 'cancelling' END, "
                         "updated_at=? WHERE id=? AND state IN ('queued','running','awaiting_approval')", (now(), job_id))
        return self.get(job_id)

    def cancel_all(self) -> int:
        with self.connect() as conn:
            return conn.execute("UPDATE jobs SET state=CASE WHEN state='queued' THEN 'cancelled' ELSE 'cancelling' END, "
                                "updated_at=? WHERE state IN ('queued','running','awaiting_approval')", (now(),)).rowcount

    def attach(self, job_id: str, owner: str, run_id: str) -> None:
        with self.connect() as conn:
            changed = conn.execute("UPDATE jobs SET run_id=?,updated_at=? WHERE id=? AND owner=? AND state='running'",
                                   (run_id, now(), job_id, owner)).rowcount
        if not changed:
            raise RuntimeError("Job ownership lost before start.")

    def finish(self, job_id: str, state: str, error: str | None = None) -> str:
        if state not in TERMINAL:
            raise ValueError("Invalid terminal job state")
        with self.connect() as conn:
            conn.execute("UPDATE jobs SET state=?,error=?,approval=NULL,decision=NULL,updated_at=?,finished_at=? "
                         "WHERE id=? AND state IN ('running','awaiting_approval','cancelling')",
                         (state, error, now(), now(), job_id))
            row = conn.execute("SELECT state FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise FileNotFoundError("Job not found")
        return row["state"]

    def recover(self) -> list[dict[str, Any]]:
        jobs = []
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute("SELECT * FROM jobs WHERE state IN ('running','awaiting_approval','cancelling')").fetchall()
            jobs = [self._decode(row) for row in rows]
            conn.execute("UPDATE jobs SET state='interrupted',error='Scheduler stopped; retry starts a fresh run.', "
                         "approval=NULL,decision=NULL,updated_at=?,finished_at=? "
                         "WHERE state IN ('running','awaiting_approval','cancelling')", (now(), now()))
        return jobs

    def heartbeat(self, owner: str) -> None:
        import time
        with self.connect() as conn:
            conn.execute("INSERT OR REPLACE INTO scheduler VALUES(1,?,?)", (owner, time.time()))

    def owned(self, job_id: str, owner: str) -> bool:
        import time
        with self.connect() as conn:
            row = conn.execute("SELECT j.owner,j.state,s.owner AS scheduler_owner,s.heartbeat FROM jobs j "
                               "JOIN scheduler s ON s.id=1 WHERE j.id=?", (job_id,)).fetchone()
        return bool(row and row["owner"] == row["scheduler_owner"] == owner
                    and row["state"] in {"running", "awaiting_approval"} and time.time() - row["heartbeat"] < 15)

    def request_approval(self, job_id: str, approval: dict[str, Any]) -> None:
        with self.connect() as conn:
            changed = conn.execute("UPDATE jobs SET state='awaiting_approval',approval=?,decision=NULL,updated_at=? "
                                   "WHERE id=? AND state='running'", (json.dumps(approval), now(), job_id)).rowcount
        if not changed:
            raise RuntimeError("Job stopped before approval.")

    def decide(self, job_id: str, ticket: str, approve: bool) -> dict[str, Any]:
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT state,approval,decision FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not row or row["state"] != "awaiting_approval" or row["decision"] is not None:
                raise ValueError("No pending approval for this job.")
            if json.loads(row["approval"])["ticket"] != ticket:
                raise ValueError("Approval is stale; refresh this job.")
            conn.execute("UPDATE jobs SET decision=?,updated_at=? WHERE id=?", (int(approve), now(), job_id))
        return self.get(job_id)

    def consume_decision(self, job_id: str) -> bool | None:
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT state,decision FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not row or row["state"] != "awaiting_approval" or row["decision"] is None:
                return None
            conn.execute("UPDATE jobs SET state='running',approval=NULL,decision=NULL,updated_at=? WHERE id=?", (now(), job_id))
        return bool(row["decision"])
