from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import JSONResponse

from app.core.config import settings
from app.db.session import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)) -> JSONResponse:
    """
    Check application and database health.

    Returns:
    - 200 with status=ok when everything is healthy
    - 503 with status=degraded when the DB is unreachable

    Also includes app version and environment for operational visibility.
    """
    db_status = "ok"
    http_status = 200

    try:
        await db.execute(text("SELECT 1"))
    except OperationalError:
        db_status = "error"
        http_status = 503

    return JSONResponse(
        status_code=http_status,
        content={
            "status": "ok" if http_status == 200 else "degraded",
            "db": db_status,
            "version": settings.APP_VERSION,
            "env": settings.ENV,
        },
    )
