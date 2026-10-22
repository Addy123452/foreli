"""Pydantic request/response models for the Foreli API."""
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from .utils import normalize_dt

TaskStatus = Literal["todo", "in_progress", "done", "cancelled"]
Priority = Literal["low", "medium", "high", "urgent"]


class TaskBase(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: Optional[str] = Field(default=None, max_length=5000)
    status: TaskStatus = "todo"
    priority: Priority = "medium"
    due_at: Optional[str] = None
    scheduled_at: Optional[str] = None
    estimated_minutes: Optional[int] = Field(default=None, ge=1, le=10080)
    tags: List[str] = Field(default_factory=list)

    @field_validator("due_at", "scheduled_at", mode="before")
    @classmethod
    def _normalize_datetimes(cls, value):
        return normalize_dt(value)


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=300)
    description: Optional[str] = Field(default=None, max_length=5000)
    status: Optional[TaskStatus] = None
    priority: Optional[Priority] = None
    due_at: Optional[str] = None
    scheduled_at: Optional[str] = None
    estimated_minutes: Optional[int] = Field(default=None, ge=1, le=10080)
    tags: Optional[List[str]] = None

    @field_validator("due_at", "scheduled_at", mode="before")
    @classmethod
    def _normalize_datetimes(cls, value):
        return normalize_dt(value)


class Task(TaskBase):
    id: int
    created_at: str
    updated_at: str
    completed_at: Optional[str] = None


RiskLevel = Literal["low", "medium", "high"]
PredictionStatus = Literal["active", "resolved"]


class Prediction(BaseModel):
    id: int
    type: str
    title: str
    risk_level: RiskLevel
    probability: Optional[float] = None
    explanation: str
    factors: List[str] = Field(default_factory=list)
    recommendation: Optional[str] = None
    horizon: Optional[str] = None
    related_task_ids: List[int] = Field(default_factory=list)
    status: PredictionStatus
    actual_outcome: Optional[str] = None
    feedback: Optional[str] = None
    created_at: str
    resolved_at: Optional[str] = None


FeedbackChoice = Literal["accurate", "partial", "inaccurate"]


class FeedbackIn(BaseModel):
    feedback: FeedbackChoice
    outcome: Optional[str] = Field(default=None, max_length=2000)


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=200)

    @field_validator("email", mode="before")
    @classmethod
    def _normalize_email(cls, value):
        if not isinstance(value, str):
            return value
        value = value.strip().lower()
        if "@" not in value or "." not in value.split("@")[-1]:
            raise ValueError("Enter a valid email address")
        return value


class ForgotIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)

    @field_validator("email", mode="before")
    @classmethod
    def _normalize_email(cls, value):
        if not isinstance(value, str):
            return value
        value = value.strip().lower()
        if "@" not in value or "." not in value.split("@")[-1]:
            raise ValueError("Enter a valid email address")
        return value


class ResetIn(BaseModel):
    token: str = Field(min_length=10, max_length=300)
    password: str = Field(min_length=8, max_length=200)
