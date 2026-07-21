from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.clients import router as clients_router
from app.api.v1.servers import router as servers_router

router = APIRouter()

router.include_router(auth_router)
router.include_router(servers_router)
router.include_router(clients_router)
