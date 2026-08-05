from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from app.db.session import get_db
from app.db.models import User, AutomationJob, CreatedAccountRecord
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
    proxy: Optional[str] = None
    consent_acknowledged: bool = False
    platform: str = "instagram"  # "instagram" or "facebook"


class JobOut(BaseModel):
    id: int
    job_type: str
    target: str
    status: str
    created_at: datetime


class CreatedAccountOut(BaseModel):
    id: int
    platform: str
    username: str
    email: str
    full_name: Optional[str] = None
    success: bool
    error: Optional[str] = None
    proxy: Optional[str] = None
    created_at: datetime


# ---- Background task wrappers ----

def _run_instagram_creator(user_id: int, count: int, proxy: Optional[str], db_url: str):
    """Run in BackgroundTask. Re-opens its own DB session."""
    from app.db.session import SessionLocal
    from app.experimental.instagram_creator import create_batch

    db = SessionLocal()
    try:
        results = create_batch(count=count, proxy=proxy)
        for r in results:
            try:
                r.driver.quit()
            except Exception:
                pass
            acc = r.account
            rec = CreatedAccountRecord(
                user_id=user_id,
                platform="instagram",
                username=acc.username,
                email=acc.email,
                password=acc.password,
                full_name=acc.full_name,
                extra={"cookies_file": acc.cookies_file},
                success=acc.success,
                error=acc.error,
                proxy=acc.proxy,
            )
            db.add(rec)
        db.commit()
    finally:
        db.close()


def _run_facebook_creator(user_id: int, count: int, proxy: Optional[str], db_url: str):
    from app.db.session import SessionLocal
    from app.experimental.facebook_creator import create_batch

    db = SessionLocal()
    try:
        results = create_batch(count=count, proxy=proxy)
        for r in results:
            try:
                r.driver.quit()
            except Exception:
                pass
            acc = r.account
            rec = CreatedAccountRecord(
                user_id=user_id,
                platform="facebook",
                username=f"{acc.first_name}.{acc.last_name}",
                email=acc.email,
                password=acc.password,
                full_name=f"{acc.first_name} {acc.last_name}",
                extra={
                    "fbid": acc.fbid,
                    "cookies_file": acc.cookies_file,
                    "birthday": acc.birthday,
                    "gender": acc.gender,
                },
                success=acc.success,
                error=acc.error,
                proxy=acc.proxy,
            )
            db.add(rec)
        db.commit()
    finally:
        db.close()


# ---- Endpoints ----

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


@router.post("/accounts/create", response_model=list[CreatedAccountOut])
@experimental_endpoint()
def create_accounts(data: AccountCreateIn, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db),
                    background_tasks: BackgroundTasks = None):
    """Queue account creation in a background task.

    Returns the list of newly-created account records AFTER background
    completes — but to keep API responsive, this returns immediately
    and the client polls GET /api/experimental/accounts to see results.

    For synchronous (blocking) behavior, query ?wait=true — still
    experimental and not recommended for count > 1.
    """
    require_explicit_consent(data.consent_acknowledged)
    if data.count < 1 or data.count > 10:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="count must be between 1 and 10")
    if data.platform not in ("instagram", "facebook"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="platform must be 'instagram' or 'facebook'")

    if data.platform == "instagram":
        background_tasks.add_task(
            _run_instagram_creator, user.id, data.count, data.proxy, settings.database_url
        )
    else:
        background_tasks.add_task(
            _run_facebook_creator, user.id, data.count, data.proxy, settings.database_url
        )

    return [CreatedAccountOut(
        id=0, platform=data.platform, username="(pending)",
        email="(pending)", full_name=None, success=False,
        error="Background task queued — poll GET /api/experimental/accounts for results",
        proxy=data.proxy, created_at=datetime.utcnow(),
    )]


@router.get("/accounts", response_model=list[CreatedAccountOut])
@experimental_endpoint()
def list_created_accounts(platform: Optional[str] = None,
                          user: User = Depends(get_current_user),
                          db: Session = Depends(get_db)):
    q = db.query(CreatedAccountRecord).filter(CreatedAccountRecord.user_id == user.id)
    if platform:
        q = q.filter(CreatedAccountRecord.platform == platform)
    rows = q.order_by(CreatedAccountRecord.created_at.desc()).limit(200).all()
    return [CreatedAccountOut(
        id=r.id, platform=r.platform, username=r.username or "",
        email=r.email or "", full_name=r.full_name, success=r.success,
        error=r.error, proxy=r.proxy, created_at=r.created_at,
    ) for r in rows]


@router.get("/bot/jobs", response_model=list[JobOut])
@experimental_endpoint()
def list_bot_jobs(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(AutomationJob).filter(AutomationJob.user_id == user.id).order_by(
        AutomationJob.created_at.desc()).limit(100).all()
    return [JobOut(id=j.id, job_type=j.job_type, target=j.target,
                   status=j.status, created_at=j.created_at) for j in rows]