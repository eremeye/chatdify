import logging
import os

from fastapi import FastAPI

from app.api import chatwoot, health, webhooks
from app.api.webhooks import lifespan
from app.utils.sentry import init_sentry

# Add before creating FastAPI app
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

# Initialize Sentry with comprehensive integrations
sentry_initialized = init_sentry(
    with_fastapi=True,
    with_asyncpg=True,
    with_celery=True,
    with_httpx=True,
    with_sqlalchemy=True,
)

if sentry_initialized:
    logging.info("Sentry initialized with comprehensive integrations: FastAPI, AsyncPG, Celery, HTTPX, and SQLAlchemy")

app = FastAPI(title="Chatdify", lifespan=lifespan, debug=os.getenv("DEBUG", "False") == "True")

app.include_router(webhooks.router, prefix="/api/v1")
app.include_router(health.router, prefix="/api/v1/health")
app.include_router(chatwoot.router, prefix="/api/v1")
