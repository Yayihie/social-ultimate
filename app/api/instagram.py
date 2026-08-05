from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
import bleach

from app.db.session import get_db
from app.db.models import User, InstagramAccount
from app.core.security import get_current_user
from app.core.instagram import (
    InstagramClient, build_oauth_url, exchange_code_for_token,
    InstagramGraphError,
)

router = APIRouter(prefix="/api/instagram", tags=["instagram"])


class ConnectOut(BaseModel):
    url: str


@router.get("/oauth/start", response_model=ConnectOut)
def oauth_start(user: User = Depends(get_current_user)):
    try:
        return {"url": build_oauth_url(state=str(user.id))}
    except InstagramGraphError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))


@router.get("/oauth/callback")
async def oauth_callback(code: str = Query(...), state: str = Query(...),
                         db: Session = Depends(get_db)):
    try:
        token_data = await exchange_code_for_token(code)
    except InstagramGraphError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    user = db.query(User).get(int(state))
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid state")
    account = InstagramAccount(
        user_id=user.id,
        ig_user_id=token_data.get("user_id", ""),
        access_token=token_data["access_token"],
        token_expires_at=datetime.utcnow() + __import__("datetime").timedelta(seconds=token_data.get("expires_in", 5184000)),
    )
    db.add(account)
    db.commit()
    return {"ok": True, "ig_user_id": account.ig_user_id}


@router.get("/accounts")
def list_accounts(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(InstagramAccount).filter(InstagramAccount.user_id == user.id).all()


@router.get("/accounts/{account_id}/me")
async def get_me(account_id: int, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    account = db.query(InstagramAccount).filter(
        InstagramAccount.id == account_id, InstagramAccount.user_id == user.id
    ).first()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    client = InstagramClient(account.access_token, account.ig_user_id)
    try:
        return await client.get_me()
    except InstagramGraphError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
    finally:
        await client.close()


@router.get("/accounts/{account_id}/insights")
async def get_insights(account_id: int, period: str = "day",
                       user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    account = db.query(InstagramAccount).filter(
        InstagramAccount.id == account_id, InstagramAccount.user_id == user.id
    ).first()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    client = InstagramClient(account.access_token, account.ig_user_id)
    try:
        return await client.get_user_insights(period=period)
    except InstagramGraphError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
    finally:
        await client.close()


@router.get("/accounts/{account_id}/media")
async def list_media(account_id: int, limit: int = 20,
                     user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    account = db.query(InstagramAccount).filter(
        InstagramAccount.id == account_id, InstagramAccount.user_id == user.id
    ).first()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    client = InstagramClient(account.access_token, account.ig_user_id)
    try:
        return await client.get_recent_media(limit=limit)
    except InstagramGraphError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
    finally:
        await client.close()


class PublishIn(BaseModel):
    account_id: int
    image_url: str
    caption: str


@router.post("/publish")
async def publish(data: PublishIn, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    account = db.query(InstagramAccount).filter(
        InstagramAccount.id == data.account_id, InstagramAccount.user_id == user.id
    ).first()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    # XSS protection on caption (Instagram renders captions as text, but our DB stores them)
    safe_caption = bleach.clean(data.caption, tags=[], strip=True)
    client = InstagramClient(account.access_token, account.ig_user_id)
    try:
        media_id = await client.publish_photo(data.image_url, safe_caption)
        return {"ok": True, "ig_media_id": media_id}
    except InstagramGraphError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
    finally:
        await client.close()