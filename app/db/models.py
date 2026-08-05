from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Text, JSON
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    instagram_accounts = relationship("InstagramAccount", back_populates="user")
    scheduled_posts = relationship("ScheduledPost", back_populates="user")
    automation_jobs = relationship("AutomationJob", back_populates="user")


class InstagramAccount(Base):
    __tablename__ = "instagram_accounts"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    ig_user_id = Column(String, unique=True, index=True)
    ig_username = Column(String, index=True)
    access_token = Column(Text, nullable=False)
    token_expires_at = Column(DateTime)
    account_type = Column(String, default="BUSINESS")  # BUSINESS or CREATOR
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="instagram_accounts")
    posts = relationship("ScheduledPost", back_populates="account")


class ScheduledPost(Base):
    __tablename__ = "scheduled_posts"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    account_id = Column(Integer, ForeignKey("instagram_accounts.id"), nullable=False)
    caption = Column(Text)
    media_url = Column(String)
    media_type = Column(String, default="IMAGE")  # IMAGE, VIDEO, CAROUSEL
    scheduled_for = Column(DateTime, nullable=False, index=True)
    status = Column(String, default="pending")  # pending, posted, failed
    posted_at = Column(DateTime)
    ig_media_id = Column(String)
    error = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="scheduled_posts")
    account = relationship("InstagramAccount", back_populates="posts")


class AutomationJob(Base):
    """Experimental automation job (igbot-style). Disabled unless EXPERIMENTAL_ENABLED."""
    __tablename__ = "automation_jobs"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    job_type = Column(String, nullable=False)  # follow_unfollow, like_by_tag, comment
    target = Column(String)  # tag, user, or location
    config = Column(JSON)  # job-specific options
    status = Column(String, default="queued")  # queued, running, completed, failed, aborted
    started_at = Column(DateTime)
    finished_at = Column(DateTime)
    error = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="automation_jobs")


class CreatedAccountRecord(Base):
    """Track accounts created via the experimental creator modules."""
    __tablename__ = "created_accounts"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    platform = Column(String, nullable=False, index=True)  # "instagram" or "facebook"
    username = Column(String, index=True)
    email = Column(String)
    password = Column(Text)  # stored plaintext because this is an experimental tool
    full_name = Column(String)
    extra = Column(JSON)  # fbid, cookies_file path, mailbox backend, sid_token, etc.
    success = Column(Boolean, default=False)
    error = Column(Text)
    proxy = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class InboxSnapshot(Base):
    """Captured inbox state during account creation.

    One row per poll. Lets you see what we received, extract codes, and
    debug why verification failed.
    """
    __tablename__ = "inbox_snapshots"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    account_record_id = Column(Integer, ForeignKey("created_accounts.id"), nullable=True)
    backend = Column(String, index=True)  # "guerrillamail", "emailfake", "console"
    email_address = Column(String, index=True)
    sender = Column(String)
    subject = Column(String)
    body_excerpt = Column(Text)
    body_full = Column(Text)
    extracted_codes = Column(JSON)  # list[str]
    message_id = Column(String)
    captured_at = Column(DateTime, default=datetime.utcnow, index=True)
    event = Column(String, default="message_received")  # message_received, poll_tick, poll_error, no_mail


class AnalyticsSnapshot(Base):
    __tablename__ = "analytics_snapshots"
    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("instagram_accounts.id"), nullable=False)
    followers = Column(Integer)
    follows = Column(Integer)
    media_count = Column(Integer)
    reach = Column(Integer)
    impressions = Column(Integer)
    profile_views = Column(Integer)
    captured_at = Column(DateTime, default=datetime.utcnow, index=True)