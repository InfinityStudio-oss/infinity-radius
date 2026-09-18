from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_router
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.integrations.selcom_business.config import validate_selcom_startup_config
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.request_id import RequestIDMiddleware

settings = get_settings()

configure_logging()

# Fails loud at boot on a sandbox/production Selcom credential mismatch —
# never waits for the first real withdrawal to discover it. No-op if
# Selcom isn't configured at all yet (a valid, safe "not set up" state).
validate_selcom_startup_config()

app = FastAPI(
    title=settings.app_name,
    description="Multi-Tenant ISP Billing & WiFi Management Platform — tenant API",
    version="0.1.0",
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url=None,
)

register_exception_handlers(app)

# Middleware order: the LAST one added wraps outermost, so RequestIDMiddleware
# (added last) sees every request first and every response last — every
# response, including CORS/rate-limit rejections, carries an X-Request-ID.
app.add_middleware(
    RateLimitMiddleware,
    redis_url=str(settings.redis_url),
    limit=settings.rate_limit_requests,
    window_seconds=settings.rate_limit_window_seconds,
)

if settings.cors_allow_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.add_middleware(RequestIDMiddleware)

app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {"service": settings.app_name, "status": "running"}
