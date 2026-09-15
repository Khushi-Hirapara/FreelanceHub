from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.models import (
    ContractStatus,
    DisputeResolution,
    DisputeStatus,
    MilestoneStatus,
    PaymentMethod,
    PaymentStatus,
    ProjectStatus,
    ProposalStatus,
    UserRole,
)


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


class RatingSummary(BaseModel):
    average: float = 0.0
    count: int = 0


class PublicUserOut(BaseModel):
    """Directory / public profile card. No email, password, or auth fields."""

    id: int
    name: str
    role: UserRole | None = None
    title: str | None = None
    location: str | None = None
    bio: str | None = None
    hourly_rate: float | None = None
    skills: list[str] = []
    ratings: RatingSummary
    # Compatibility aliases for existing frontend cards
    rating_avg: float = 0.0
    rating_count: int = 0
    projects_done: int = 0


class RecommendedFreelancerOut(BaseModel):
    freelancer: PublicUserOut
    match_score: int
    matched_skills: list[str] = []
    reasons: list[str] = []


class UserPage(BaseModel):
    items: list[PublicUserOut]
    page: int
    limit: int
    total: int
    pages: int


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


class PortfolioItemCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    project_url: str | None = Field(default=None, max_length=500)
    image_url: str | None = Field(default=None, max_length=500)

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("Title is required")
        return text

    @field_validator("description")
    @classmethod
    def blank_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None

    @field_validator("project_url", "image_url")
    @classmethod
    def http_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return _http_url(text or None)


class PortfolioItemUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    project_url: str | None = Field(default=None, max_length=500)
    image_url: str | None = Field(default=None, max_length=500)

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if not text:
            raise ValueError("Title is required")
        return text

    @field_validator("description")
    @classmethod
    def blank_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None

    @field_validator("project_url", "image_url")
    @classmethod
    def http_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return _http_url(text or None)


class PortfolioItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    title: str
    description: str | None = None
    project_url: str | None = None
    image_url: str | None = None
    created_at: datetime
    updated_at: datetime


def _http_url(value: str | None) -> str | None:
    if not value:
        return None
    from urllib.parse import urlparse

    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("URL must start with http:// or https://")
    return value


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


def _clean_skills(value: list[str] | None) -> list[str] | None:
    if value is None:
        return None
    cleaned = []
    for skill in value:
        text = str(skill).strip()
        if not text:
            continue
        if len(text) > 40:
            raise ValueError("Each skill must be 40 characters or fewer")
        if text not in cleaned:
            cleaned.append(text)
    if len(cleaned) > 20:
        raise ValueError("A project can have at most 20 skills")
    return cleaned


class ProjectCreate(BaseModel):
    title: str = Field(min_length=5, max_length=200)
    category: str = Field(min_length=2, max_length=80)
    description: str = Field(min_length=20)
    skills: list[str] = []
    budget_min: float = Field(gt=0)
    budget_max: float = Field(gt=0)
    deadline: date | None = None
    experience_level: str | None = None

    @field_validator("skills")
    @classmethod
    def clean_skills(cls, value: list[str]) -> list[str]:
        return _clean_skills(value) or []

    @field_validator("budget_max")
    @classmethod
    def budget_range(cls, value: float, info) -> float:
        minimum = info.data.get("budget_min")
        if minimum is not None and value < minimum:
            raise ValueError("budget_max must be >= budget_min")
        return value


class ProjectBriefRequest(BaseModel):
    description: str = Field(min_length=10, max_length=4000)

    @field_validator("description")
    @classmethod
    def strip_description(cls, value: str) -> str:
        text = value.strip()
        if len(text) < 10:
            raise ValueError("description must be at least 10 characters")
        return text


class ProjectBriefOut(BaseModel):
    title: str
    category: str
    description: str
    skills: list[str]
    experience_level: str
    budget_min: float
    budget_max: float
    estimated_duration: str


class AiChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)

    @field_validator("content")
    @classmethod
    def strip_content(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("content cannot be empty")
        return text


class AiChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: list[AiChatTurn] = Field(default_factory=list, max_length=12)

    @field_validator("message")
    @classmethod
    def strip_message(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("message cannot be empty")
        return text


class AiChatOut(BaseModel):
    reply: str


class ProjectUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=5, max_length=200)
    category: str | None = Field(default=None, min_length=2, max_length=80)
    description: str | None = Field(default=None, min_length=20)
    skills: list[str] | None = None
    budget_min: float | None = Field(default=None, gt=0)
    budget_max: float | None = Field(default=None, gt=0)
    deadline: date | None = None
    experience_level: str | None = Field(default=None, max_length=40)
    status: ProjectStatus | None = None

    @field_validator("title", "category", "description", "experience_level")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None

    @field_validator("skills")
    @classmethod
    def clean_skills(cls, value: list[str] | None) -> list[str] | None:
        return _clean_skills(value)

    @model_validator(mode="after")
    def budget_order(self) -> "ProjectUpdate":
        if self.budget_min is not None and self.budget_max is not None and self.budget_max < self.budget_min:
            raise ValueError("budget_max must be >= budget_min")
        return self


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
    client: PublicUserOut | None = None


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
    contract_id: int | None = None
    freelancer: PublicUserOut | None = None
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


class ContractPartyOut(BaseModel):
    """Public party fields only — no email or password hash."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    role: UserRole
    title: str | None = None
    location: str | None = None


class ContractProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    category: str
    status: ProjectStatus


class ContractCreate(BaseModel):
    proposal_id: int


class ContractStatusUpdate(BaseModel):
    status: ContractStatus


class PaymentOut(BaseModel):
    id: int
    contract_id: int
    milestone_id: int | None = None
    client_id: int
    freelancer_id: int
    amount: float
    platform_fee: float
    freelancer_amount: float
    currency: str
    payment_method: PaymentMethod
    transaction_id: str | None = None
    status: PaymentStatus
    paid_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    contract_status: ContractStatus | None = None
    project: ContractProjectOut | None = None
    client: ContractPartyOut | None = None
    freelancer: ContractPartyOut | None = None


class ReviewCreate(BaseModel):
    contract_id: int
    rating: int = Field(ge=1, le=5)
    comment: str = Field(min_length=1, max_length=2000)


class ReviewUpdate(BaseModel):
    rating: int | None = Field(default=None, ge=1, le=5)
    comment: str | None = Field(default=None, min_length=1, max_length=2000)


class ReviewerOut(BaseModel):
    """Public reviewer fields only — no email."""

    id: int
    name: str
    role: UserRole


class ReviewOut(BaseModel):
    id: int
    contract_id: int
    reviewer_id: int
    reviewee_id: int
    rating: int
    comment: str
    created_at: datetime
    updated_at: datetime
    reviewer: ReviewerOut | None = None
    project_title: str | None = None


class MilestoneCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    amount: float = Field(gt=0)
    due_date: date | None = None
    order_index: int | None = Field(default=None, ge=0)


class MilestoneUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    amount: float | None = Field(default=None, gt=0)
    due_date: date | None = None
    order_index: int | None = Field(default=None, ge=0)


class MilestoneStatusUpdate(BaseModel):
    status: MilestoneStatus


class MilestoneOut(BaseModel):
    id: int
    contract_id: int
    title: str
    description: str | None = None
    amount: float
    order_index: int
    status: MilestoneStatus
    due_date: date | None = None
    submitted_at: datetime | None = None
    approved_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    payment_id: int | None = None
    payment_status: PaymentStatus | None = None
    payment_paid_at: datetime | None = None
    payment_released_at: datetime | None = None
    payment_transaction_id: str | None = None


class ContractOut(BaseModel):
    id: int
    project_id: int
    proposal_id: int
    client_id: int
    freelancer_id: int
    agreed_amount: float
    platform_fee: float
    freelancer_amount: float
    currency: str
    status: ContractStatus
    start_date: date | None = None
    end_date: date | None = None
    created_at: datetime
    updated_at: datetime
    project: ContractProjectOut | None = None
    client: ContractPartyOut | None = None
    freelancer: ContractPartyOut | None = None


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    title: str
    message: str
    related_type: str | None = None
    related_id: int | None = None
    is_read: bool
    created_at: datetime


class UnreadCountOut(BaseModel):
    count: int


class ReadAllOut(BaseModel):
    updated: int


class AttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    uploader_id: int
    project_id: int | None = None
    contract_id: int | None = None
    conversation_id: int | None = None
    milestone_id: int | None = None
    filename: str
    content_type: str
    size: int
    created_at: datetime
    uploader_name: str | None = None


class AdminDashboardOut(BaseModel):
    total_users: int
    clients: int
    freelancers: int
    projects: int
    active_contracts: int
    completed_contracts: int
    total_payment_volume: float
    platform_revenue: float
    pending_disputes: int


class AdminUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: EmailStr
    role: UserRole
    title: str | None = None
    location: str | None = None
    is_active: bool
    is_verified: bool = False
    rating_avg: float = 0.0
    rating_count: int = 0
    projects_done: int = 0
    created_at: datetime


class AdminUserStatusUpdate(BaseModel):
    is_active: bool


class AdminProjectOut(BaseModel):
    id: int
    title: str
    category: str
    status: ProjectStatus
    client_id: int
    client_name: str | None = None
    budget_min: float
    budget_max: float
    proposal_count: int = 0
    created_at: datetime


class AdminContractOut(BaseModel):
    id: int
    project_id: int
    project_title: str | None = None
    client_id: int
    client_name: str | None = None
    freelancer_id: int
    freelancer_name: str | None = None
    agreed_amount: float
    platform_fee: float
    status: ContractStatus
    created_at: datetime


class AdminPaymentOut(BaseModel):
    id: int
    contract_id: int
    milestone_id: int | None = None
    client_id: int
    freelancer_id: int
    amount: float
    platform_fee: float
    freelancer_amount: float
    status: PaymentStatus
    transaction_id: str | None = None
    paid_at: datetime | None = None
    created_at: datetime
    project_title: str | None = None


class DisputeCreate(BaseModel):
    reason: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=10, max_length=8000)


class DisputeUpdate(BaseModel):
    reason: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = Field(default=None, min_length=10, max_length=8000)
    status: DisputeStatus | None = None


class DisputeResolve(BaseModel):
    outcome: DisputeStatus
    resolution: DisputeResolution | None = None
    partial_amount: float | None = Field(default=None, gt=0)
    notes: str | None = Field(default=None, max_length=4000)

    @field_validator("outcome")
    @classmethod
    def outcome_closed(cls, value: DisputeStatus) -> DisputeStatus:
        if value not in (DisputeStatus.resolved, DisputeStatus.rejected):
            raise ValueError("outcome must be resolved or rejected")
        return value


class DisputeOut(BaseModel):
    id: int
    contract_id: int
    opened_by: int
    reason: str
    description: str
    status: DisputeStatus
    resolution: DisputeResolution | None = None
    resolution_notes: str | None = None
    partial_amount: float | None = None
    resolved_by: int | None = None
    resolved_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    project_title: str | None = None
    opener_name: str | None = None
    resolver_name: str | None = None
    contract_status: ContractStatus | None = None


class AdminDisputeOut(BaseModel):
    kind: str = "dispute"
    id: int
    status: str
    title: str
    reason: str
    description: str
    contract_id: int
    project_id: int | None = None
    opened_by: int
    client_id: int
    freelancer_id: int
    resolution: str | None = None
    resolution_notes: str | None = None
    partial_amount: float | None = None
    updated_at: datetime | None = None
    created_at: datetime


class AdminPage(BaseModel):
    items: list[Any]
    page: int
    limit: int
    total: int
    pages: int


TokenResponse.model_rebuild()
