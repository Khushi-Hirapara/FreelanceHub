from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.routers import (
    admin,
    ai,
    attachments,
    auth,
    contracts,
    disputes,
    messages,
    milestones,
    notifications,
    payments,
    projects,
    proposals,
    reviews,
    stats,
    users,
    ws,
)

logger = logging.getLogger("freelancehub")
settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Schema changes belong in Alembic migrations (`alembic upgrade head`), not create_all.
    yield


app = FastAPI(
    title="FreelanceHub API",
    description="REST API for the FreelanceHub freelance marketplace",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    openapi_url=None if settings.is_production else "/openapi.json",
)

# Bearer-token auth (no cookies). Origins come from CORS_ORIGINS — never "*" in production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list or ["http://localhost:5500"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(projects.router, prefix="/api")
app.include_router(ai.router, prefix="/api")
app.include_router(proposals.router, prefix="/api")
app.include_router(contracts.router, prefix="/api")
app.include_router(disputes.router, prefix="/api")
app.include_router(reviews.router, prefix="/api")
app.include_router(payments.router, prefix="/api")
app.include_router(milestones.router, prefix="/api")
app.include_router(messages.router, prefix="/api")
app.include_router(stats.router, prefix="/api")
app.include_router(notifications.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(attachments.router, prefix="/api")
app.include_router(ws.router, prefix="/api")


def _jsonable_validation_errors(errors: list) -> list:
    cleaned = []
    for item in errors:
        entry = {
            "type": item.get("type"),
            "loc": item.get("loc"),
            "msg": item.get("msg"),
        }
        cleaned.append(entry)
    return cleaned


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"detail": _jsonable_validation_errors(exc.errors())},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    logger.exception("Unhandled server error")
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected error occurred. Please try again later."},
    )


@app.get("/")
def root():
    payload = {"app": "FreelanceHub API", "health": "/api/health"}
    if not settings.is_production:
        payload["docs"] = "/docs"
    return payload


@app.get("/api/health")
def health():
    return {"status": "ok", "env": settings.app_env}
