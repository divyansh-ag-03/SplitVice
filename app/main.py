import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api.v1.routes.auth import router as auth_router
from app.api.v1.routes.balances import router as balances_router
from app.api.v1.routes.expenses import router as expenses_router
from app.api.v1.routes.groups import router as groups_router
from app.api.v1.routes.health import router as health_router
from app.api.v1.routes.settlements import router as settlements_router
from app.api.v1.routes.users import router as users_router
from app.core.config import settings
from app.core.exceptions import AppException
from app.core.logging_config import configure_logging
from app.core.middleware import RequestLoggingMiddleware, SecurityHeadersMiddleware
from app.db.session import engine
from app.web.routes import router as web_router

# Configure logging before anything else
configure_logging()
logger = logging.getLogger(__name__)

# ── Optional Sentry integration ───────────────────────────────────────────────
# Enabled only when SENTRY_DSN is set in the environment.
# Captures unhandled exceptions and sends them to Sentry.
if settings.SENTRY_DSN:
    try:
        import sentry_sdk
        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            environment=settings.ENV,
            release=settings.APP_VERSION,
            # Capture 100% of transactions in production; adjust as needed
            traces_sample_rate=0.1,
        )
        logger.info("Sentry initialised (env=%s)", settings.ENV)
    except ImportError:
        logger.warning(
            "SENTRY_DSN is set but sentry-sdk is not installed. "
            "Run: pip install sentry-sdk"
        )


async def _check_migration_version() -> None:
    """Warn at startup if the DB schema is behind the latest Alembic revision."""
    try:
        alembic_cfg = AlembicConfig("alembic.ini")
        script = ScriptDirectory.from_config(alembic_cfg)
        head = script.get_current_head()

        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT version_num FROM alembic_version LIMIT 1")
            )
            row = result.fetchone()
            current = row[0] if row else None

        if current != head:
            logger.warning(
                "DB schema is NOT at the latest migration. "
                "Current: %s | Head: %s — run `alembic upgrade head`",
                current,
                head,
            )
        else:
            logger.info("DB schema is up to date (revision: %s)", current)
    except Exception as exc:
        logger.warning("Could not check migration version: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    db_display = (
        settings.DATABASE_URL.split("@")[-1]
        if "@" in settings.DATABASE_URL
        else settings.DATABASE_URL
    )
    logger.info(
        "Starting SplitVice v%s | env=%s | debug=%s | db=%s",
        settings.APP_VERSION,
        settings.ENV,
        settings.DEBUG,
        db_display,
    )
    await _check_migration_version()
    yield


app = FastAPI(
    title="SplitVice",
    version=settings.APP_VERSION,
    docs_url="/api/v1/docs",
    openapi_url="/api/v1/openapi.json",
    lifespan=lifespan,
)

# ── Middleware (applied in reverse order — last added = outermost) ────────────
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

# ── Static files ──────────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(groups_router)
app.include_router(expenses_router)
app.include_router(balances_router)
app.include_router(settlements_router)
app.include_router(web_router)


# ── Exception handlers ────────────────────────────────────────────────────────

@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "status": exc.status_code},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "Unhandled exception on %s %s",
        request.method,
        request.url.path,
        exc_info=exc,
    )
    # Forward to Sentry if configured
    if settings.SENTRY_DSN:
        try:
            import sentry_sdk
            sentry_sdk.capture_exception(exc)
        except Exception:
            pass

    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "status": 500},
    )
