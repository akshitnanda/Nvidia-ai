"""The browser can choose workflows and limits, never commands or filesystem roots."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.runtime import WorkflowMode


class JobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task: str = Field(min_length=1, max_length=8000)
    mode: WorkflowMode = WorkflowMode.PLAN
    provider: Literal["demo", "configured"] = "demo"
    scenario: Literal["standard", "repair_demo"] = "standard"
    apply_changes: bool = False
    max_repairs: int = Field(default=0, ge=0, le=3)
    max_seconds: int = Field(default=900, ge=10, le=3600)
    max_model_calls: int = Field(default=24, ge=1, le=100)
    max_total_tokens: int = Field(default=200_000, ge=100, le=2_000_000)

    @model_validator(mode="after")
    def validate_options(self) -> "JobRequest":
        self.task = self.task.strip()
        if not self.task:
            raise ValueError("A task is required.")
        if self.apply_changes and self.mode != WorkflowMode.IMPLEMENT:
            raise ValueError("Only implementation workflows apply changes.")
        if self.max_repairs and not self.apply_changes:
            raise ValueError("Repair attempts require file application.")
        if self.scenario == "repair_demo" and not (self.provider == "demo" and self.mode == WorkflowMode.IMPLEMENT and self.apply_changes and self.max_repairs >= 1):
            raise ValueError("The repair demo requires demo implementation, isolated application, and at least one repair.")
        return self


class ApprovalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticket: str = Field(min_length=1, max_length=64)
    approve: bool
