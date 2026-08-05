from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import User, ScheduledPost, InstagramAccount
from app.core.security import get_current_user
from app.scheduler.jobs import schedule_post_publish
import bleach

router = APIRouter(prefix="/api/posts", tags=["posts"])


class PostIn(BaseModel):
    account_id: int
    caption: str
    media_url: str
    media_type: str = "IMAGE"  # IMAGE, VIDEO
    scheduled_for: datetime


class PostOut(BaseModel):
    id: int
    status: str
    scheduled_for: datetime
    ig_media_id: str | None = None


@router.post("", response_model=PostOut)
def create_post(data: PostIn, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    account = db.query(InstagramAccount).filter(
        InstagramAccount.id == data.account_id, InstagramAccount.user_id == user.id
    ).first()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    if data.scheduled_for < datetime.utcnow():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="scheduled_for must be in the future")
    safe_caption = bleach.clean(data.caption, tags=[], strip=True)
    post = ScheduledPost(
        user_id=user.id,
        account_id=account.id,
        caption=safe_caption,
        media_url=data.media_url,
        media_type=data.media_type,
        scheduled_for=data.scheduled_for,
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    schedule_post_publish(post)
    return PostOut(id=post.id, status=post.status, scheduled_for=post.scheduled_for)


@router.get("", response_model=list[PostOut])
def list_posts(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(ScheduledPost).filter(ScheduledPost.user_id == user.id).order_by(
        ScheduledPost.scheduled_for.desc()).limit(100).all()
    return [PostOut(id=p.id, status=p.status, scheduled_for=p.scheduled_for,
                    ig_media_id=p.ig_media_id) for p in rows]


@router.delete("/{post_id}")
def delete_post(post_id: int, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    post = db.query(ScheduledPost).filter(
        ScheduledPost.id == post_id, ScheduledPost.user_id == user.id).first()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if post.status != "pending":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Cannot delete post in status '{post.status}'")
    db.delete(post)
    db.commit()
    return {"ok": True}