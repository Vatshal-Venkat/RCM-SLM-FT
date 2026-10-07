from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class HistoryTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class ChatOptions(BaseModel):
    max_tokens: int | None = Field(default=None, ge=16, le=1024)
    temperature: float | None = Field(default=None, ge=0.0, le=1.5)
    use_rag: bool = True


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: list[HistoryTurn] = Field(default_factory=list, max_length=20)
    options: ChatOptions = Field(default_factory=ChatOptions)

    @field_validator("message")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("message must not be blank")
        return v


class IntentOut(BaseModel):
    intent: str
    confidence: float
    terms: list[str]
    entities: dict[str, list[str]]


class SourceOut(BaseModel):
    ref: int
    title: str
    document: str
    section: str | None = None
    score: float
    snippet: str


class ValidationIssueOut(BaseModel):
    code: str
    severity: Literal["info", "warning", "error"]
    message: str


class ValidationOut(BaseModel):
    passed: bool
    regenerated: bool = False
    issues: list[ValidationIssueOut] = Field(default_factory=list)


class UsageOut(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0


class ChatResponse(BaseModel):
    answer: str
    intent: IntentOut
    sources: list[SourceOut] = Field(default_factory=list)
    validation: ValidationOut
    grounded: bool
    model: str | None
    usage: UsageOut
    timings_ms: dict[str, float]
    # Structured analytics behind the answer (tables/charts for the UI), when the question was about data.
    data: dict[str, Any] | None = None
