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