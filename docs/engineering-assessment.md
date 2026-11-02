# Engineering assessment

Assessment baseline: commit `4b0b086` (package version 0.1.2). This change focuses on execution reliability and useful run evidence.

## Findings and implemented changes

| Priority | Baseline finding | Resulting behavior |
| --- | --- | --- |
| High | Preview and rejected-approval runs could execute model-generated shell commands. | Validation requires applied changes and uses only operator-configured test/lint commands. Suggestions remain visible artifacts. |
| High | Validation failures returned `success=true`; CLI callers could not reliably detect them. | Failed commands produce failed workflow status, explicit validation status, and exit code 1. Timeouts become failed command results. |
| High | Context scanning could read `.env`, keys, Git-ignored files, and binary content. | Shared secret-path filters, Git-aware enumeration, symlink boundaries, binary handling, and filtered diffs. |
| High | Auto-commit used `git add -A`, including unrelated work. | Scoped staging, refusal of existing staged changes, mandatory passing validation, and review call completion before commit. |
| High | Conflicting file proposals could silently overwrite one another. | Combined path/content preflight rejects duplicate and nested destinations before writes. |
| Medium | Local NIM override still checked the model's cloud endpoint for authentication. | Effective local mode determines both URL and authentication; no cloud key is required. |
| Medium | All provider errors were retried, with a sleep even after the final failure. | Transient HTTP/transport retries only, bounded numeric Retry-After support, immediate invalid-response errors, and a reused HTTP client per completion. |
| Medium | Generated run artifacts could trigger watch mode indefinitely. | Shared exclusions plus the configured data directory filter prevent artifact feedback loops. |
| Medium | Failures and partial agent work were difficult to inspect. | Run manifests, persisted results, immediate agent artifacts, timestamped events, and per-run usage. Reusing an orchestrator creates a distinct run. |
| Medium | Dashboard hardcoded `data/runs`, exposed raw artifacts, and trusted paths/content. | Configured storage, safe bounded artifact reads, pagination, searchable summaries, text-only artifact rendering, and responsive detail view. |
| Performance | Independent test and docs handoffs were sequential. | Both run concurrently after the coder proposal; no latency benchmark is claimed. |

## Verification

- Regression suite covers preview/apply decisions, failed validation, skipped commits, context filters, protected paths, conflicting changes, JSON CLI history, watch exclusions, transient provider failures, local NIM routing, malformed responses, and bounded artifact reads.
- Git tests use temporary repositories to verify scoped commits, protection of staged work, literal path arguments, and revision handling without a shell.
- Browser checks cover run selection, artifact selection, search/no-results/clear, refresh, error logs, and a 390px mobile viewport.
- Demo execution is local and deterministic. Provider behavior is tested through HTTP mocks; live NVIDIA model quality, availability, and latency are not verified.

## Next investments

1. **Isolated worktrees and transactional application.** Current writes are preflighted and backed up but can still partially apply on an I/O failure. Host validation executes project code. Add per-run worktrees and a controlled execution environment before unattended use.
2. **Structured review decisions and repair loops.** Review is prose and advisory. Define a findings schema and an explicit blocking decision before automated revisions or quality-gated commits.
3. **Live model evaluation.** Benchmark representative repositories, grounded plans, compilable patches, and cost/latency using the actual configured NVIDIA models. Demo output cannot establish model quality.
4. **Context budget and content redaction.** Path filtering reduces accidental disclosure, but credentials embedded in source, task text, prior memory, and arbitrary command output are not automatically scrubbed. Add explicit context previews and token budgeting.
5. **Durable job recovery.** A hard-killed process may leave `running` state. Add heartbeats and resumable jobs before extending the read-only dashboard into a workflow launcher.

The dashboard remains a local read-only tool without authentication; remote multi-user hosting is outside this change.
