from contextlib import asynccontextmanager

from fastapi import FastAPI

from decoded.config import settings
from decoded.logging import configure_logging, logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.log_level)
    logger.info("startup", app=settings.app_name, version=settings.version)
    yield
    logger.info("shutdown")


app = FastAPI(
    title="Decoded API",
    description="Turn AI papers into content everyone understands.",
    version=settings.version,
    lifespan=lifespan,
)


@app.get("/v1/health")
async def health() -> dict:
    return {"status": "ok", "version": settings.version}


@app.get("/")
async def root() -> dict:
    return {"name": "Decoded API", "docs": "/docs", "health": "/v1/health"}