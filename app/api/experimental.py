from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import User, AutomationJob, AnalyticsSnapshot, InstagramAccount
from app.core.security import get_current_user
from app.core.experimental_gate import experimental_endpoint, require_explicit_consent
from app.core.config import settings

router = APIRouter(prefix="/api/experimental", tags=["experimental"])


class BotJobIn(BaseModel):
    job_type: str  # follow_unfollow, like_by_tag, comment
    target: str
    config: dict = {}
    consent_acknowledged: bool = False


class AccountCreateIn(BaseModel):
    count: int = 1
    proxy: str | None = None
    consent_acknowledged: bool = False


class JobOut(BaseModel):
    id: int
    job_type: str
    target: str
    status: str
    created_at: datetime


@router.post("/bot/jobs", response_model=JobOut)
@experimental_endpoint()
def create_bot_job(data: BotJobIn, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    require_explicit_consent(data.consent_acknowledged)
    job = AutomationJob(
        user_id=user.id,
        job_type=data.job_type,
        target=data.target,
        config=data.config,
        status="queued",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return JobOut(id=job.id, job_type=job.job_type, target=job.target,
                  status=job.status, created_at=job.created_at)


@router.post("/accounts/create")
@experimental_endpoint()
def create_accounts(data: AccountCreateIn, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    require_explicit_consent(data.consent_acknowledged)
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=(
            "Account creation is intentionally not implemented in the public "
            "module. See docs/EXPERIMENTAL.md for the reference Selenium "
            "pattern from eaabak/instagram-auto-create-account. You must "
            "implement and review this yourself before use."
        ),
    )


@router.get("/bot/jobs", response_model=list[JobOut])
@experimental_endpoint()
def list_bot_jobs(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(AutomationJob).filter(AutomationJob.user_id == user.id).order_by(
        AutomationJob.created_at.desc()).limit(100).all()
    return [JobOut(id=j.id, job_type=j.job_type, target=j.target,
                   status=j.status, created_at=j.created_at) for j in rows]