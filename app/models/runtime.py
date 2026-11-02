from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class WorkflowMode(str, Enum):
    ANALYZE = "analyze"
    PLAN = "plan"
    IMPLEMENT = "implement"
    REVIEW = "review"
    RELEASE = "release"


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ProviderUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class CompletionRequest(BaseModel):
    profile_name: str
    model: str
    messages: list[ChatMessage]
    temperature: float = 0.2
    top_p: float = 0.95
    max_tokens: int = 4096
    timeout_seconds: int = 90
    extra_body: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CompletionResponse(BaseModel):
    model: str
    content: str
    usage: ProviderUsage = Field(default_factory=ProviderUsage)
    raw_response: dict[str, Any] = Field(default_factory=dict)


class ProposedFileChange(BaseModel):
    path: str
    action: Literal["create_or_update", "delete"] = "create_or_update"
    reason: str = ""
    content: str | None = None


class ChangeSet(BaseModel):
    summary: str = ""
    changes: list[ProposedFileChange] = Field(default_factory=list)
    commands: list[str] = Field(default_factory=list)


class CommandExecution(BaseModel):
    command: str
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    duration_seconds: float = 0.0


class AgentResult(BaseModel):
    agent: str
    model: str
    output: str
    artifacts: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ReviewFinding(BaseModel):
    severity: Literal["critical", "high", "medium", "low", "info"]
    title: str = Field(min_length=1)
    detail: str = Field(min_length=1)
    path: str | None = None
    line: int | None = Field(default=None, ge=1)


class ReviewReport(BaseModel):
    verdict: Literal["approve", "request_changes"]
    summary: str = Field(min_length=1)
    findings: list[ReviewFinding]
    residual_risks: list[str]

    @property
    def approved(self) -> bool:
        return self.verdict == "approve" and not any(
            finding.severity in {"critical", "high"} for finding in self.findings
        )


ReviewStatus = Literal["not_run", "approved", "changes_requested", "invalid"]


class ImplementationAttempt(BaseModel):
    number: int
    changed_files: list[str]
    validation_status: Literal["not_run", "passed", "failed"]
    review_status: ReviewStatus
    review: ReviewReport | None = None
    command_results: list[CommandExecution] = Field(default_factory=list)


class WorkflowResult(BaseModel):
    run_id: str
    mode: WorkflowMode
    success: bool
    summary: str
    outputs: dict[str, str] = Field(default_factory=dict)
    changed_files: list[str] = Field(default_factory=list)
    command_results: list[CommandExecution] = Field(default_factory=list)
    validation_status: Literal["not_run", "passed", "failed"] = "not_run"
    suggested_commands: list[str] = Field(default_factory=list)
    review_status: ReviewStatus = "not_run"
    review: ReviewReport | None = None
    attempts: list[ImplementationAttempt] = Field(default_factory=list)
    application_status: Literal["not_requested", "declined", "applied", "no_changes"] = "not_requested"
    workspace_path: str | None = None
    workspace_branch: str | None = None

