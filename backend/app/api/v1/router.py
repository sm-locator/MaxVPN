from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.clients import router as clients_router
from app.api.v1.servers import router as servers_router
from app.api.v1.smart_routing import router as smart_routing_router
from app.api.v1.smart_routing_apply import (
    router as smart_routing_apply_router,
)
from app.api.v1.smart_routing_dependency_diagnostic import (
    router as smart_routing_dependency_diagnostic_router,
)
from app.api.v1.smart_routing_dependency_groups import (
    router as smart_routing_dependency_groups_router,
)
from app.api.v1.smart_routing_domain_diagnostic import (
    router as smart_routing_domain_diagnostic_router,
)
from app.api.v1.smart_routing_import import router as smart_routing_import_router
from app.api.v1.smart_routing_presets import (
    router as smart_routing_presets_router,
)
from app.api.v1.smart_routing_sync import router as smart_routing_sync_router
from app.api.v1.status import router as status_router
from app.api.v1.vless import router as vless_router
from app.api.v1.vpn import router as vpn_router

router = APIRouter()

router.include_router(auth_router)
router.include_router(servers_router)
router.include_router(clients_router)
router.include_router(smart_routing_router)
router.include_router(smart_routing_sync_router)
router.include_router(smart_routing_import_router)
router.include_router(smart_routing_domain_diagnostic_router)
router.include_router(smart_routing_dependency_diagnostic_router)
router.include_router(smart_routing_dependency_groups_router)
router.include_router(smart_routing_apply_router)
router.include_router(smart_routing_presets_router)
router.include_router(status_router)
router.include_router(vpn_router)
router.include_router(vless_router)
