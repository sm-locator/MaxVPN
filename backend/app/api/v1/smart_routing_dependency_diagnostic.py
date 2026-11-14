from __future__ import annotations

import ipaddress

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, IPvAnyAddress
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, require_role
from app.database.dependencies import get_db
from app.models.roles import UserRole
from app.models.smart_routing_rule import SmartRoutingRule
from app.models.user import User
from app.repositories.smart_routing_dependency_group import (
    SmartRoutingDependencyGroupRepository,
)
from app.repositories.smart_routing_rule import SmartRoutingRuleRepository
from backend.application.container import (
    build_smart_routing_dependency_diagnostic_session_service,
    get_settings,
)
from backend.infrastructure.ssh.ssh_remote_command_executor import (
    SSHRemoteCommandExecutor,
)
from backend.services.smart_routing_dependency_diagnostic import (
    DependencyDiagnosticResource,
)
from backend.services.smart_routing_dependency_diagnostic_service import (
    SmartRoutingDependencyDiagnosticService,
)
from backend.services.smart_routing_dependency_diagnostic_session import (
    SmartRoutingDependencyDiagnosticSessionService,
)
from backend.services.smart_routing_target_validation import validate_domain_target

router = APIRouter(
    prefix="/smart-routing",
    dependencies=[Depends(require_role(UserRole.ADMIN))],
    tags=["Smart Routing"],
)


# Current Docker Compose address of maxvpn-frontend (Nginx). Trust X-Real-IP
# only when the TCP peer is this exact proxy, not merely any private IP.
TRUSTED_PROXY_PEER_IPS = frozenset({ipaddress.ip_address("172.18.0.4")})


class DependencyDiagnosticStart(BaseModel):
    site_domain: str = Field(min_length=1, max_length=255)
    client_ip: IPvAnyAddress | None = None
    duration_seconds: int = Field(default=30, ge=20, le=60)


class DependencyDiagnosticCommit(BaseModel):
    hostnames: list[str] = Field(min_length=1, max_length=100)
    title: str | None = Field(default=None, max_length=255)


def _resolve_client_ip(request: Request) -> str:
    """Resolve the LAN client IP, honoring X-Real-IP only from a private proxy peer.

    The MaxVPN frontend Nginx overwrites X-Real-IP with its observed peer address.
    X-Forwarded-For is deliberately not used because the proxy appends to that
    header and its leftmost value may have been supplied by the caller.
    """
    client = request.client
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Не удалось определить IP клиента. Укажите IP вручную.",
        )

    try:
        peer_ip = ipaddress.ip_address(client.host)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Не удалось определить IP клиента. Укажите IP вручную.",
        ) from exc

    host = request.headers.get("host", "").split(":", 1)[0].strip("[]").lower()
    if host == "localhost" or host in {"127.0.0.1", "::1"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "IP клиента не определяется автоматически при открытии панели "
                "через localhost. Откройте MaxVPN по адресу maxvpn.lan "
                "или укажите IP вручную."
            ),
        )

    trusted_proxy_peer = peer_ip in TRUSTED_PROXY_PEER_IPS
    forwarded_ip = request.headers.get("x-real-ip", "").strip()
    if forwarded_ip and not trusted_proxy_peer:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Нельзя безопасно определить IP клиента через неизвестный прокси. "
                "Укажите IP клиента вручную."
            ),
        )
    if trusted_proxy_peer and forwarded_ip:
        try:
            resolved_ip = ipaddress.ip_address(forwarded_ip)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Прокси передал некорректный IP клиента. Укажите IP вручную.",
            ) from exc
        if (
            resolved_ip.is_unspecified
            or resolved_ip.is_multicast
            or resolved_ip.is_loopback
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "IP клиента не определяется автоматически при открытии панели "
                    "через localhost. Откройте MaxVPN по адресу maxvpn.lan "
                    "или укажите IP вручную."
                ),
            )
        return str(resolved_ip)

    if peer_ip.is_loopback:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "IP клиента не определяется автоматически при открытии панели "
                "через localhost. Откройте MaxVPN по адресу maxvpn.lan "
                "или укажите IP вручную."
            ),
        )

    if peer_ip.is_unspecified or peer_ip.is_multicast:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Не удалось определить IP клиента. Укажите IP вручную.",
        )

    return str(peer_ip)


def get_session_service() -> SmartRoutingDependencyDiagnosticSessionService:
    return build_smart_routing_dependency_diagnostic_session_service()


def get_runtime_executor() -> SSHRemoteCommandExecutor:
    settings = get_settings()

    return SSHRemoteCommandExecutor(
        host=settings.ssh_host,
        username=settings.ssh_username,
        private_key_path=settings.ssh_private_key_path,
        port=settings.ssh_port,
    )


def get_repository(
    db: Session = Depends(get_db),
) -> SmartRoutingRuleRepository:
    return SmartRoutingRuleRepository(db)


def get_group_repository(
    db: Session = Depends(get_db),
) -> SmartRoutingDependencyGroupRepository:
    return SmartRoutingDependencyGroupRepository(db)


def read_direct_ips(
    executor: SSHRemoteCommandExecutor,
    *,
    strict: bool = False,
) -> set[str]:
    result = executor.run(
        [
            "ipset",
            "list",
            "MAXVPN_DIRECT",
        ]
    )

    if result.returncode != 0:
        if strict:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "Не удалось проверить MAXVPN_DIRECT; добавление из диагностики "
                    "запрещено."
                ),
            )
        return set()

    addresses: set[str] = set()
    in_members = False
    found_members = False

    for line in (result.stdout or "").splitlines():
        stripped = line.strip()

        if stripped == "Members:":
            in_members = True
            found_members = True
            continue

        if not in_members or not stripped:
            continue

        try:
            address = ipaddress.ip_address(stripped)
        except ValueError:
            continue

        if address.version == 4:
            addresses.add(str(address))

    if strict and not found_members:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ответ MAXVPN_DIRECT неполон; добавление из диагностики запрещено.",
        )
    return addresses


def _normalize_hostname(value: str) -> str:
    try:
        return validate_domain_target(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid hostname: {value!r}",
        ) from exc


def _resource_map(resources: tuple[DependencyDiagnosticResource | object, ...]):
    return {
        str(resource.hostname).lower().rstrip("."): resource for resource in resources
    }


@router.post(
    "/dependency-diagnostic/start",
    status_code=status.HTTP_200_OK,
)
def start_dependency_diagnostic(
    data: DependencyDiagnosticStart,
    request: Request,
    current_user: User = Depends(get_current_user),
    service: SmartRoutingDependencyDiagnosticSessionService = Depends(
        get_session_service,
    ),
) -> dict[str, object]:
    del current_user

    try:
        client_ip = (
            str(data.client_ip)
            if data.client_ip is not None
            else _resolve_client_ip(request)
        )
        return service.start(
            site_domain=data.site_domain,
            client_ip=client_ip,
            duration_seconds=data.duration_seconds,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.get(
    "/dependency-diagnostic/{token}",
    status_code=status.HTTP_200_OK,
)
def poll_dependency_diagnostic(
    token: str,
    current_user: User = Depends(get_current_user),
    service: SmartRoutingDependencyDiagnosticSessionService = Depends(
        get_session_service,
    ),
    executor: SSHRemoteCommandExecutor = Depends(
        get_runtime_executor,
    ),
    repository: SmartRoutingRuleRepository = Depends(
        get_repository,
    ),
) -> dict[str, object]:
    try:
        rules = repository.get_by_user(current_user.id)
        direct_rules = tuple(
            rule.target
            for rule in rules
            if rule.enabled
            and str(getattr(rule.action, "value", rule.action)) == "direct"
            and str(getattr(rule.target_type, "value", rule.target_type)) == "domain"
        )

        direct_ips = read_direct_ips(executor, strict=True)

        payload, _ = service.poll(
            token,
            direct_ips=direct_ips,
            direct_rules=direct_rules,
        )

        return payload

    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.post(
    "/dependency-diagnostic/{token}/rules",
    status_code=status.HTTP_201_CREATED,
)
def commit_dependency_diagnostic_rules(
    token: str,
    data: DependencyDiagnosticCommit,
    current_user: User = Depends(get_current_user),
    service: SmartRoutingDependencyDiagnosticSessionService = Depends(
        get_session_service,
    ),
    repository: SmartRoutingRuleRepository = Depends(get_repository),
    group_repository: SmartRoutingDependencyGroupRepository = Depends(
        get_group_repository,
    ),
    executor: SSHRemoteCommandExecutor = Depends(get_runtime_executor),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    try:
        group = service.get_group(token)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    normalized = []
    seen: set[str] = set()
    resources = _resource_map(group.resources)
    existing_rules = repository.get_by_user(current_user.id)
    direct_ips = read_direct_ips(executor, strict=True)
    enabled_direct_rules = tuple(
        str(rule.target).strip().lower().rstrip(".")
        for rule in existing_rules
        if bool(rule.enabled)
        and str(getattr(rule.action, "value", rule.action)) == "direct"
        and str(getattr(rule.target_type, "value", rule.target_type)) == "domain"
    )

    for hostname in data.hostnames:
        value = _normalize_hostname(hostname)
        if value in seen:
            continue
        seen.add(value)
        resource = resources.get(value)
        if resource is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Hostname was not observed by diagnostic: {value}",
            )
        if not bool(getattr(resource, "candidate_for_direct", False)):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Hostname is not an allowed DIRECT candidate: {value}",
            )
        allowed_now = SmartRoutingDependencyDiagnosticService.is_selectable_now(
            hostname=value,
            site_domain=group.site_domain,
            ips=getattr(resource, "ips", ()),
            direct_ips=direct_ips,
            direct_rules=enabled_direct_rules,
            synthetic=bool(getattr(resource, "synthetic", False)),
        )
        if not allowed_now:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Hostname is no longer eligible for diagnostic DIRECT "
                    f"selection: {value}"
                ),
            )
        normalized.append(value)

    direct_by_target = {
        str(rule.target).strip().lower().rstrip("."): rule
        for rule in existing_rules
        if str(getattr(rule.action, "value", rule.action)) == "direct"
        and str(getattr(rule.target_type, "value", rule.target_type)) == "domain"
        and str(getattr(rule.address_family, "value", rule.address_family)) == "any"
    }

    next_priority = (
        max(
            (int(rule.priority) for rule in existing_rules),
            default=0,
        )
        + 1
    )

    created_rules: list[SmartRoutingRule] = []
    reused_rules: list[SmartRoutingRule] = []

    try:
        dependency_group = group_repository.get_or_create(
            current_user.id,
            group.site_domain,
            title=(data.title or group.site_domain).strip() or group.site_domain,
        )

        for hostname in normalized:
            rule = direct_by_target.get(hostname)
            if rule is None:
                rule = SmartRoutingRule(
                    user_id=current_user.id,
                    target_type="domain",
                    target=hostname,
                    action="direct",
                    priority=next_priority,
                    address_family="any",
                    enabled=True,
                )
                next_priority += 1
                db.add(rule)
                db.flush()
                direct_by_target[hostname] = rule
                created_rules.append(rule)
            else:
                reused_rules.append(rule)

            group_repository.add_rule(
                dependency_group,
                rule.id,
                source="diagnostic",
            )

        db.commit()
        db.refresh(dependency_group)

    except Exception:
        db.rollback()
        raise

    def rule_payload(rule: SmartRoutingRule) -> dict[str, object]:
        return {
            "id": rule.id,
            "target_type": str(getattr(rule.target_type, "value", rule.target_type)),
            "target": rule.target,
            "action": str(getattr(rule.action, "value", rule.action)),
            "priority": rule.priority,
            "address_family": str(
                getattr(rule.address_family, "value", rule.address_family)
            ),
            "enabled": bool(rule.enabled),
        }

    return {
        "token": token,
        "site_domain": group.site_domain,
        "group_id": dependency_group.id,
        "created_rules": [rule_payload(rule) for rule in created_rules],
        "reused_rules": [rule_payload(rule) for rule in reused_rules],
        "rule_ids": [rule.id for rule in [*created_rules, *reused_rules]],
        "apply_required": True,
    }
