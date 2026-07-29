from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models import ProjectStatus, ProposalStatus, UserRole


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserOut"


class RegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: UserRole

    @field_validator("role")
    @classmethod
    def register_roles(cls, value: UserRole) -> UserRole:
        if value == UserRole.admin:
            raise ValueError("Cannot self-register as admin")
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    role: UserRole | None = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: EmailStr
    role: UserRole
    title: str | None = None
    location: str | None = None
    bio: str | None = None
    hourly_rate: float | None = None
    skills: list[str] = []
    avatar_url: str | None = None
    is_verified: bool = False
    rating_avg: float = 0.0
    rating_count: int = 0
    projects_done: int = 0
    on_time_pct: float = 100.0
    created_at: datetime


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    title: str | None = None
    location: str | None = None
    bio: str | None = None
    hourly_rate: float | None = Field(default=None, ge=0)
    skills: list[str] | None = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class ProjectCreate(BaseModel):
    title: str = Field(min_length=5, max_length=200)
    category: str = Field(min_length=2, max_length=80)
    description: str = Field(min_length=20)
    skills: list[str] = []
    budget_min: float = Field(gt=0)
    budget_max: float = Field(gt=0)
    deadline: date | None = None
    experience_level: str | None = None

    @field_validator("budget_max")
    @classmethod
    def budget_range(cls, value: float, info) -> float:
        minimum = info.data.get("budget_min")
        if minimum is not None and value < minimum:
            raise ValueError("budget_max must be >= budget_min")
        return value


class ProjectUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=5, max_length=200)
    category: str | None = None
    description: str | None = Field(default=None, min_length=20)
    skills: list[str] | None = None
    budget_min: float | None = Field(default=None, gt=0)
    budget_max: float | None = Field(default=None, gt=0)
    deadline: date | None = None
    experience_level: str | None = None
    status: ProjectStatus | None = None


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    client_id: int
    title: str
    category: str
    description: str
    skills: list[str] = []
    budget_min: float
    budget_max: float
    deadline: date | None = None
    experience_level: str | None = None
    status: ProjectStatus
    proposal_count: int = 0
    created_at: datetime
    client: UserOut | None = None


class MilestoneIn(BaseModel):
    description: str = Field(min_length=1, max_length=300)
    amount: float = Field(ge=0)


class ProposalCreate(BaseModel):
    project_id: int
    bid_amount: float = Field(gt=0)
    estimated_duration: str | None = None
    cover_letter: str = Field(min_length=30, max_length=1200)
    milestones: list[MilestoneIn] = []


class ProposalStatusUpdate(BaseModel):
    status: ProposalStatus


class ProposalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    freelancer_id: int
    bid_amount: float
    estimated_duration: str | None = None
    cover_letter: str
    milestones: list[Any] = []
    status: ProposalStatus
    created_at: datetime
    freelancer: UserOut | None = None
    project: ProjectOut | None = None


class MessageCreate(BaseModel):
    receiver_id: int
    message_text: str = Field(min_length=1, max_length=5000)
    conversation_id: int | None = None
    project_id: int | None = None


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    conversation_id: int
    sender_id: int
    receiver_id: int
    message_text: str
    is_read: bool
    created_at: datetime


class ConversationOut(BaseModel):
    id: int
    other_user: UserOut
    project_id: int | None = None
    project_tag: str | None = None
    last_message: str | None = None
    unread_count: int = 0
    updated_at: datetime


TokenResponse.model_rebuild()
