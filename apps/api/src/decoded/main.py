from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from decoded.api.papers import router as papers_router
from decoded.config import settings
from decoded.logging import configure_logging, logger
from decoded.api.search import router as search_router
from decoded.api.users import router as users_router
from decoded.observability.tracing import flush as flush_tracing
from decoded.observability.tracing import init_tracing
from decoded.api.modes import router as modes_router
from decoded.cache.client import close_redis, get_redis
from decoded.api.topics import router as topics_router
from decoded.api.people import router as people_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.log_level)
    init_tracing()
    await get_redis()  # conecta cedo, loga se falhar
    logger.info("startup", app=settings.app_name, version=settings.version)
    yield
    await close_redis()
    flush_tracing()
    logger.info("shutdown")

app = FastAPI(
    title="Decoded API",
    description="Turn AI papers into content everyone understands.",
    version=settings.version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(papers_router)
app.include_router(search_router)
app.include_router(users_router)
app.include_router(modes_router)
app.include_router(topics_router)
app.include_router(people_router)

@app.get("/v1/health")
async def health() -> dict:
    return {"status": "ok", "version": settings.version}


@app.get("/")
async def root() -> dict:
    return {"name": "Decoded API", "docs": "/docs", "health": "/v1/health"}