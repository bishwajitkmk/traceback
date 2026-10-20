from fastapi import APIRouter

from app.api.v1.routes import auth, cases, health, incidents, ingest, projects, replay

api_router = APIRouter(prefix="/api/v1")
for module in (health, auth, projects, incidents, replay, cases, ingest):
    api_router.include_router(module.router)
