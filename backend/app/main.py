from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.repositories import router as repositories_router
from app.core.config import get_settings
from app.db.init_db import initialize_database_schema


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    initialize_database_schema()
    yield


app = FastAPI(title="RepoPilot", lifespan=lifespan)
settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_cors_origins,
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(repositories_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
