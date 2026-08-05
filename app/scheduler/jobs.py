"""APScheduler integration. Wakes up to publish scheduled posts."""
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger

from app.db.session import SessionLocal
from app.db.models import ScheduledPost, AutomationJob
from app.core.instagram import InstagramClient, InstagramGraphError
from app.core.experimental_gate import experimental_endpoint

scheduler = AsyncIOScheduler()


async def publish_scheduled_post(post_id: int) -> None:
    db = SessionLocal()
    try:
        post = db.query(ScheduledPost).filter(ScheduledPost.id == post_id).first()
        if not post or post.status != "pending":
            return
        account = post.account
        client = InstagramClient(account.access_token, account.ig_user_id)
        try:
            ig_media_id = await client.publish_photo(post.media_url, post.caption or "")
            post.status = "posted"
            post.ig_media_id = ig_media_id
            post.posted_at = datetime.utcnow()
        except InstagramGraphError as e:
            post.status = "failed"
            post.error = str(e)
        finally:
            await client.close()
            db.commit()
    finally:
        db.close()


async def run_automation_job(job_id: int) -> None:
    """Stub: real implementation in experimental/instabot.py with consent."""
    db = SessionLocal()
    try:
        job = db.query(AutomationJob).filter(AutomationJob.id == job_id).first()
        if not job:
            return
        job.status = "failed"
        job.error = "Automation jobs are experimental-only and require EXPERIMENTAL_ENABLED=true. See docs/EXPERIMENTAL.md."
        job.finished_at = datetime.utcnow()
        db.commit()
    finally:
        db.close()


def schedule_post_publish(post: ScheduledPost) -> None:
    scheduler.add_job(
        publish_scheduled_post,
        trigger=DateTrigger(run_date=post.scheduled_for),
        args=[post.id],
        id=f"post-{post.id}",
        replace_existing=True,
    )


def start_scheduler():
    if not scheduler.running:
        scheduler.start()


def shutdown_scheduler():
    if scheduler.running:
        scheduler.shutdown()