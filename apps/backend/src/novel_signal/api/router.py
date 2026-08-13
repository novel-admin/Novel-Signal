from fastapi import APIRouter

from novel_signal.api.v1.health import router as health_router
from novel_signal.modules.registry import module_routers
from novel_signal.sources.router import router as sources_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(sources_router)

for router in module_routers:
    api_router.include_router(router)
