# Mission control

Mission control turns the run viewer into a local workflow launcher. Start it from your chosen workspace:

```powershell
swarm dashboard --root .
```

Open `http://127.0.0.1:8787/`. **Launch workflow** queues a task; **Job queue** shows its lifecycle; **Inspect run** opens the evidence. Plans, analysis, reviews, and release notes use the configured workspace. Implementation is preview-only unless **Apply in an isolated branch** is selected.

## First walkthrough without an API key

1. Start from a Git repository root with at least one commit.
2. Choose **Try the approval & repair demo**, then **Queue workflow**.
3. Inspect the proposed diff and select **Approve this diff**.
4. The demo runs real Python compilation on its isolated proposal. The first scripted proposal contains a syntax error and fails validation.
5. Inspect and approve the repair. Compilation now passes. **Inspect run** shows both attempts and their actual validation results.

The demo proposes `swarm_demo_example.py` inside its retained worktree and uses an application-defined Python compilation command. It does not run model-suggested commands or call a live endpoint. Other demo workflows keep their original scripted behavior. Demo usage is estimated and cannot establish live-model quality.

## Approvals and stop controls

Every managed application, including every repair, pauses for explicit approval. `SWARM_AUTO_APPLY` does not bypass browser approvals. Approvals carry a one-time ticket and a SHA-256 receipt for the displayed diff. Old tickets and duplicate decisions are rejected. Files that change while approval is pending require a fresh run and diff.

**Decline & stop** cancels the run. **Cancel** stops one queued or active job; **Cancel all** applies to this workspace's pending and active jobs. The supervisor stops the worker and its observed process descendants. Worktrees and evidence remain available. Managed jobs never auto-commit or merge changes.

## Durable queue and recovery

Job state lives in `SWARM_DATA_DIR/jobs.sqlite3`, with worker logs in `SWARM_DATA_DIR/jobs/`. Each data directory is bound to one workspace, and an OS-backed lock allows one supervisor to own its queue. Workers also check scheduler ownership and heartbeats before model calls and file application.

Queued jobs survive restarts. Active jobs found after a restart are marked **Interrupted** and are not automatically replayed. **Retry as new run** creates a new job with a link to its predecessor and a fresh run/worktree, starting from committed `HEAD` when the worker begins. Source edits and `.env` are not copied. Direct CLI runs outside the queue do not have this supervisor/recovery mechanism.

## Limits

| Setting | Default | Meaning |
| --- | --- | --- |
| `SWARM_JOB_CONCURRENCY` | `2` | Managed workers, range 1–4 |
| `SWARM_JOB_MAX_SECONDS` | `1800` | Operator runtime cap; job default 900 seconds |
| `SWARM_JOB_MAX_CALLS` | `48` | Operator cap on model requests; job default 24 |
| `SWARM_JOB_MAX_TOKENS` | `500000` | Operator cap on reported tokens; job default 200000 |
| `SWARM_MAX_CONTEXT_BYTES` | `80000` | Per-agent context JSON byte budget |

The runtime limit includes approval waits. Each HTTP retry/fallback consumes a model-request allowance. Concurrent agents share one call counter. Reported-token limits block new requests once reached; an in-flight response or concurrent responses may exceed that limit, at which point the job stops with **Limit reached**. Missing or inaccurate provider usage cannot establish a hard token or spending limit.

Oversized context is clipped into valid JSON with explicit truncation markers; per-agent budget artifacts record whether that happened. Validation output is bounded and output overflow fails the command. Validation timeouts stop the observed command process tree.

## CLI queue controls

```powershell
swarm submit "Plan endpoint coverage" --mode plan --provider demo
swarm submit "Implement endpoint coverage" --mode implement --provider configured --apply --max-repairs 2 --max-model-calls 20
swarm jobs
swarm jobs <job-id>
swarm jobs <job-id> --cancel
swarm jobs <job-id> --retry
```

The dashboard must be running to process jobs and collect file approvals. An operator cap below a CLI default lowers that default automatically. Requests that explicitly exceed a cap are rejected.

## Local API

`GET /control` returns server capabilities and a session token for same-origin control. `GET /jobs` and `GET /jobs/{id}` inspect jobs. JSON writes require the `X-Swarm-Token` header:

- `POST /jobs`: queue a `JobRequest`.
- `POST /jobs/{id}/approval`: submit `{ticket, approve}` for the current diff.
- `POST /jobs/{id}/cancel`: cancel one job.
- `POST /jobs/cancel-all`: cancel this queue's active and pending jobs.
- `POST /jobs/{id}/retry`: create a fresh job from a terminal job.

The API enforces loopback clients and allowed hosts, rejects cross-origin writes, and accepts only fixed workflow options. It does not accept shell commands, repository paths, provider URLs, or credentials from the browser. Configuration is provided to workers through their environment rather than the job database or command line.

`/docs` serves a bundled API reference and links to `/openapi.json`; it loads no third-party scripts. `/health` reports a degraded status when the supervisor is unavailable.

## Execution boundaries

This is a single-user local tool. Remote multi-user hosting is unsupported. Worktrees separate generated files from the source checkout; they do not sandbox code, network access, credentials, or host permissions. Cancelling a local worker does not reverse file writes or guarantee termination of a request already received by a remote provider. Inspect changes and validation before integrating a run branch.

Visual desktop/mobile QA and live NVIDIA behavior require separate verification. Automated tests use real background subprocesses, temporary repositories, HTTP mocks, and scripted demo output.
