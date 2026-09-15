from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.deps import get_current_user
from app.models import Payment, PaymentStatus, Project, ProjectStatus, Proposal, ProposalStatus, User, UserRole

router = APIRouter(tags=["Stats"])


@router.get("/stats")
def platform_stats(db: Session = Depends(get_db)):
    freelancers = db.scalar(select(func.count()).select_from(User).where(User.role == UserRole.freelancer)) or 0
    clients = db.scalar(select(func.count()).select_from(User).where(User.role == UserRole.client)) or 0
    open_projects = db.scalar(
        select(func.count()).select_from(Project).where(Project.status == ProjectStatus.open)
    ) or 0
    total_projects = db.scalar(select(func.count()).select_from(Project)) or 0

    month_ago = datetime.now(timezone.utc) - timedelta(days=30)
    projects_this_month = db.scalar(
        select(func.count()).select_from(Project).where(Project.created_at >= month_ago)
    ) or 0

    avg_on_time = db.scalar(select(func.avg(User.on_time_pct)).where(User.role == UserRole.freelancer)) or 100.0
    accepted_value = db.scalar(
        select(func.coalesce(func.sum(Proposal.bid_amount), 0)).where(Proposal.status == ProposalStatus.accepted)
    ) or 0

    return {
        "freelancers": freelancers,
        "clients": clients,
        "open_projects": open_projects,
        "total_projects": total_projects,
        "projects_this_month": projects_this_month,
        "on_time_pct": round(float(avg_on_time), 1),
        "accepted_bid_total": float(accepted_value),
    }


@router.get("/dashboard/summary")
def dashboard_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role == UserRole.freelancer:
        proposals = db.scalars(
            select(Proposal)
            .options(joinedload(Proposal.project))
            .where(Proposal.freelancer_id == current_user.id)
            .order_by(Proposal.created_at.desc())
        ).unique().all()

        pending = [p for p in proposals if p.status == ProposalStatus.pending]
        accepted = [p for p in proposals if p.status == ProposalStatus.accepted]
        payments = db.scalars(
            select(Payment).where(Payment.freelancer_id == current_user.id)
        ).all()
        paid_payments = [p for p in payments if p.status == PaymentStatus.paid]
        pending_payments = [
            p for p in payments if p.status in (PaymentStatus.pending, PaymentStatus.processing)
        ]
        paid_earnings = sum(float(p.freelancer_amount) for p in paid_payments)
        pending_earnings = sum(float(p.freelancer_amount) for p in pending_payments)

        open_projects = db.scalar(
            select(func.count()).select_from(Project).where(Project.status == ProjectStatus.open)
        ) or 0

        activity = []
        for p in proposals[:8]:
            activity.append(
                {
                    "text": f"Your proposal on “{p.project.title if p.project else 'a project'}” is {p.status.value}.",
                    "time": p.created_at.isoformat(),
                }
            )

        return {
            "role": "freelancer",
            "active_bids": len(pending),
            "awaiting_reply": len(pending),
            "active_contracts": len(accepted),
            "earned": paid_earnings,
            "total_earnings": paid_earnings,
            "paid_earnings": paid_earnings,
            "pending_earnings": pending_earnings,
            "rating_avg": current_user.rating_avg,
            "rating_count": current_user.rating_count,
            "open_projects": open_projects,
            "activity": activity,
        }

    # Client / admin
    projects = db.scalars(
        select(Project)
        .options(joinedload(Project.proposals).joinedload(Proposal.freelancer))
        .where(Project.client_id == current_user.id)
        .order_by(Project.created_at.desc())
    ).unique().all()

    active = [p for p in projects if p.status not in (ProjectStatus.completed, ProjectStatus.cancelled)]
    pending_proposals = [
        prop
        for p in projects
        for prop in (p.proposals or [])
        if prop.status == ProposalStatus.pending
    ]
    accepted_spend = sum(
        prop.bid_amount
        for p in projects
        for prop in (p.proposals or [])
        if prop.status == ProposalStatus.accepted
    )
    payments = db.scalars(select(Payment).where(Payment.client_id == current_user.id)).all()
    paid_payments = [p for p in payments if p.status == PaymentStatus.paid]
    open_payments = [p for p in payments if p.status in (PaymentStatus.pending, PaymentStatus.processing)]
    total_spent = sum(float(p.amount) for p in paid_payments)

    activity = []
    recent_props = sorted(pending_proposals, key=lambda x: x.created_at, reverse=True)[:8]
    for prop in recent_props:
        name = prop.freelancer.name if prop.freelancer else "A freelancer"
        title = next((p.title for p in projects if p.id == prop.project_id), "your project")
        activity.append(
            {
                "text": f"{name} submitted a proposal on “{title}”.",
                "time": prop.created_at.isoformat(),
            }
        )

    return {
        "role": "client",
        "active_projects": len(active),
        "new_proposals": len(pending_proposals),
        "total_spent": total_spent,
        "pending_payments": len(open_payments),
        "pending_payment_amount": sum(float(p.amount) for p in open_payments),
        "completed_payments": len(paid_payments),
        "accepted_bid_total": accepted_spend,
        "rating_avg": current_user.rating_avg,
        "rating_count": current_user.rating_count,
        "activity": activity,
    }
