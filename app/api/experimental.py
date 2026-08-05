from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from app.db.session import get_db, SessionLocal
from app.db.models import User, AutomationJob, CreatedAccountRecord, InboxSnapshot
from app.core.security import get_current_user
from app.core.experimental_gate import experimental_endpoint, require_explicit_consent
from app.core.config import settings

router = APIRouter(prefix="/api/experimental", tags=["experimental"])


class BotJobIn(BaseModel):
    job_type: str
    target: str
    config: dict = {}
    consent_acknowledged: bool = False


class AccountCreateIn(BaseModel):
    count: int = 1
    proxy: Optional[str] = None
    consent_acknowledged: bool = False
    platform: str = "instagram"
    mailbox_backend: str = "guerrillamail"  # guerrillamail / emailfake / console
    verification_timeout: int = 180


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
    mailbox_backend: Optional[str] = None
    mailbox_address: Optional[str] = None
    created_at: datetime


class InboxSnapshotOut(BaseModel):
    id: int
    backend: str
    email_address: str
    sender: Optional[str] = None
    subject: Optional[str] = None
    body_excerpt: Optional[str] = None
    body_full: Optional[str] = None
    extracted_codes: list = []
    message_id: Optional[str] = None
    captured_at: datetime
    event: str


# ---- Background task wrappers ----

def _run_instagram_creator(user_id: int, count: int, proxy: Optional[str],
                           mailbox_backend: str, verification_timeout: int,
                           db_url: str):
    from app.experimental.instagram_creator import create_batch
    db = SessionLocal()
    try:
        results = create_batch(count=count, user_id=user_id, db_url=db_url,
                               proxy=proxy, mailbox_backend=mailbox_backend,
                               verification_timeout=verification_timeout)
        # Records are already saved during the run (one per attempt).
        for r in results:
            try:
                r.driver.quit()
            except Exception:
                pass
    finally:
        db.close()


def _run_facebook_creator(user_id: int, count: int, proxy: Optional[str],
                          mailbox_backend: str, db_url: str):
    from app.experimental.facebook_creator import create_batch
    from app.db.models import CreatedAccountRecord
    db = SessionLocal()
    try:
        results = create_batch(count=count, user_id=user_id, db_url=db_url,
                               proxy=proxy, mailbox_backend=mailbox_backend)
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
                    "mailbox_backend": acc.mailbox_backend,
                    "mailbox_address": acc.mailbox_address,
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
        user_id=user.id, job_type=data.job_type,
        target=data.target, config=data.config, status="queued",
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
    """Queue account creation. Poll /api/experimental/accounts for results,
    /api/experimental/inbox for verification codes."""
    require_explicit_consent(data.consent_acknowledged)
    if data.count < 1 or data.count > 10:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="count must be between 1 and 10")
    if data.platform not in ("instagram", "facebook"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="platform must be 'instagram' or 'facebook'")
    if data.mailbox_backend not in ("guerrillamail", "emailfake", "console"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="mailbox_backend must be guerrillamail, emailfake, or console")

    if data.platform == "instagram":
        background_tasks.add_task(
            _run_instagram_creator, user.id, data.count, data.proxy,
            data.mailbox_backend, data.verification_timeout,
            settings.database_url,
        )
    else:
        background_tasks.add_task(
            _run_facebook_creator, user.id, data.count, data.proxy,
            data.mailbox_backend, settings.database_url,
        )

    return [CreatedAccountOut(
        id=0, platform=data.platform, username="(pending)",
        email="(pending)", full_name=None, success=False,
        error=f"Background task queued with {data.mailbox_backend} mailbox. "
              "Poll /api/experimental/accounts for results and "
              "/api/experimental/inbox for verification codes.",
        proxy=data.proxy, mailbox_backend=data.mailbox_backend,
        mailbox_address="(pending)", created_at=datetime.utcnow(),
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
        error=r.error, proxy=r.proxy,
        mailbox_backend=(r.extra or {}).get("mailbox_backend"),
        mailbox_address=(r.extra or {}).get("mailbox_address") or r.email,
        created_at=r.created_at,
    ) for r in rows]


@router.get("/accounts/{account_id}", response_model=CreatedAccountOut)
@experimental_endpoint()
def get_account(account_id: int, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    r = db.query(CreatedAccountRecord).filter(
        CreatedAccountRecord.id == account_id,
        CreatedAccountRecord.user_id == user.id,
    ).first()
    if not r:
        raise HTTPException(status_code=404, detail="Not found")
    return CreatedAccountOut(
        id=r.id, platform=r.platform, username=r.username or "",
        email=r.email or "", full_name=r.full_name, success=r.success,
        error=r.error, proxy=r.proxy,
        mailbox_backend=(r.extra or {}).get("mailbox_backend"),
        mailbox_address=(r.extra or {}).get("mailbox_address") or r.email,
        created_at=r.created_at,
    )


# ---- Inbox visibility endpoints ----

@router.get("/inbox", response_model=list[InboxSnapshotOut])
@experimental_endpoint()
def list_inbox_snapshots(
    backend: Optional[str] = None,
    account_id: Optional[int] = None,
    codes_only: bool = Query(False, description="Only show messages with extracted codes"),
    limit: int = Query(100, le=500),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """View captured inbox messages and extracted verification codes.

    Filterable by:
    - backend (guerrillamail / emailfake / console)
    - account_id (linked CreatedAccountRecord)
    - codes_only (only show messages where we extracted verification codes)
    """
    q = db.query(InboxSnapshot).filter(InboxSnapshot.user_id == user.id)
    if backend:
        q = q.filter(InboxSnapshot.backend == backend)
    if account_id:
        q = q.filter(InboxSnapshot.account_record_id == account_id)
    rows = q.order_by(InboxSnapshot.captured_at.desc()).limit(limit).all()
    out = []
    for r in rows:
        codes = r.extracted_codes or []
        if codes_only and not codes:
            continue
        out.append(InboxSnapshotOut(
            id=r.id, backend=r.backend or "", email_address=r.email_address or "",
            sender=r.sender, subject=r.subject, body_excerpt=r.body_excerpt,
            body_full=r.body_full, extracted_codes=codes,
            message_id=r.message_id, captured_at=r.captured_at, event=r.event,
        ))
    return out


@router.get("/inbox/latest-codes")
@experimental_endpoint()
def latest_codes(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Quick view: last 20 messages that had extracted codes."""
    rows = db.query(InboxSnapshot).filter(
        InboxSnapshot.user_id == user.id,
        InboxSnapshot.event == "message_received",
    ).order_by(InboxSnapshot.captured_at.desc()).limit(50).all()
    out = []
    for r in rows:
        codes = r.extracted_codes or []
        if not codes:
            continue
        out.append({
            "id": r.id,
            "captured_at": r.captured_at.isoformat(),
            "backend": r.backend,
            "email_address": r.email_address,
            "sender": r.sender,
            "subject": r.subject,
            "codes": codes,
            "account_id": r.account_record_id,
        })
    return out[:20]


@router.get("/bot/jobs", response_model=list[JobOut])
@experimental_endpoint()
def list_bot_jobs(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(AutomationJob).filter(AutomationJob.user_id == user.id).order_by(
        AutomationJob.created_at.desc()).limit(100).all()
    return [JobOut(id=j.id, job_type=j.job_type, target=j.target,
                   status=j.status, created_at=j.created_at) for j in rows]