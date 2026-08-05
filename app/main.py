from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from contextlib import asynccontextmanager
import time

from app.core.config import settings
from app.db.session import init_db
from app.scheduler.jobs import start_scheduler, shutdown_scheduler
from app.api import auth, instagram, posts, experimental, health


# Lightweight security headers (Helmet-equivalent without the full dep)
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        return response


# Initialize DB tables eagerly (covers TestClient which may not trigger lifespan)
init_db()


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    shutdown_scheduler()


app = FastAPI(
    title="Social Ultimate",
    description=(
        "Production Instagram automation via Meta Graph API + "
        "experimental automation module (gated, opt-in)."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])

# Rate limiting on auth endpoints
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(instagram.router)
app.include_router(posts.router)
app.include_router(experimental.router)

# Serve the dashboard
import os
STATIC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "web", "public"))
os.makedirs(STATIC_DIR, exist_ok=True)  # so tests don't crash
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

from fastapi.responses import FileResponse
@app.get("/")
async def root():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))