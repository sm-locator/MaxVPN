from __future__ import annotations

import csv
import io
import ipaddress
from dataclasses import dataclass
from enum import StrEnum

from backend.services.smart_routing_target_validation import (
    validate_domain_target,
)


class SmartRoutingImportType(StrEnum):
    DOMAIN = "domain"
    CIDR = "cidr"


class SmartRoutingImportStatus(StrEnum):
    VALID = "valid"
    DUPLICATE = "duplicate"
    ALREADY_EXISTS = "already_exists"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class SmartRoutingImportItem:
    line: int
    resource: str
    target_type: SmartRoutingImportType | None
    address_family: str | None
    status: SmartRoutingImportStatus
    error: str | None = None


def _normalize_resource(value: str) -> str:
    return value.strip().strip('"').strip("'")


def _detect_resource(
    resource: str,
) -> tuple[SmartRoutingImportType, str]:
    value = _normalize_resource(resource)

    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        ip = None

    if ip is not None:
        if ip.version != 4:
            raise ValueError("IPv6 is not supported")
        return SmartRoutingImportType.CIDR, "ipv4"

    try:
        network = ipaddress.ip_network(value, strict=False)
    except ValueError:
        network = None

    if network is not None:
        if network.version != 4:
            raise ValueError("IPv6 is not supported")
        return SmartRoutingImportType.CIDR, "ipv4"

    validate_domain_target(value)
    return SmartRoutingImportType.DOMAIN, "any"


def _normalize_target(
    resource: str,
    target_type: SmartRoutingImportType,
) -> str:
    if target_type is SmartRoutingImportType.DOMAIN:
        return validate_domain_target(resource)

    value = _normalize_resource(resource)

    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        network = ipaddress.ip_network(value, strict=False)
        if network.version != 4:
            raise ValueError("IPv6 is not supported")
        return str(network)

    if ip.version != 4:
        raise ValueError("IPv6 is not supported")

    return str(ip)


def parse_txt_import(content: str) -> list[SmartRoutingImportItem]:
    items: list[SmartRoutingImportItem] = []
    seen: set[tuple[SmartRoutingImportType, str]] = set()

    for line_number, raw_line in enumerate(content.splitlines(), start=1):
        resource = _normalize_resource(raw_line)

        if not resource or resource.startswith("#"):
            continue

        try:
            target_type, address_family = _detect_resource(resource)
            normalized = _normalize_target(resource, target_type)
        except ValueError as exc:
            items.append(
                SmartRoutingImportItem(
                    line=line_number,
                    resource=resource,
                    target_type=None,
                    address_family=None,
                    status=SmartRoutingImportStatus.INVALID,
                    error=str(exc),
                )
            )
            continue

        key = (target_type, normalized)

        if key in seen:
            items.append(
                SmartRoutingImportItem(
                    line=line_number,
                    resource=normalized,
                    target_type=target_type,
                    address_family=address_family,
                    status=SmartRoutingImportStatus.DUPLICATE,
                )
            )
            continue

        seen.add(key)

        items.append(
            SmartRoutingImportItem(
                line=line_number,
                resource=normalized,
                target_type=target_type,
                address_family=address_family,
                status=SmartRoutingImportStatus.VALID,
            )
        )

    return items


def parse_csv_import(content: str) -> list[SmartRoutingImportItem]:
    reader = csv.DictReader(io.StringIO(content))

    if reader.fieldnames is None:
        raise ValueError("CSV file must contain a header")

    normalized_fields = {
        field.strip().lower() for field in reader.fieldnames if field is not None
    }

    if "resource" not in normalized_fields:
        raise ValueError("CSV file must contain a resource column")

    items: list[SmartRoutingImportItem] = []
    seen: set[tuple[SmartRoutingImportType, str]] = set()

    for line_number, row in enumerate(reader, start=2):
        raw_resource = row.get("resource")

        if raw_resource is None:
            items.append(
                SmartRoutingImportItem(
                    line=line_number,
                    resource="",
                    target_type=None,
                    address_family=None,
                    status=SmartRoutingImportStatus.INVALID,
                    error="resource is required",
                )
            )
            continue

        resource = _normalize_resource(raw_resource)

        if not resource:
            items.append(
                SmartRoutingImportItem(
                    line=line_number,
                    resource="",
                    target_type=None,
                    address_family=None,
                    status=SmartRoutingImportStatus.INVALID,
                    error="resource is required",
                )
            )
            continue

        requested_type = (row.get("type") or "").strip().lower()

        try:
            if requested_type:
                if requested_type == SmartRoutingImportType.DOMAIN.value:
                    target_type = SmartRoutingImportType.DOMAIN
                    address_family = "any"
                    validate_domain_target(resource)
                elif requested_type == SmartRoutingImportType.CIDR.value:
                    target_type = SmartRoutingImportType.CIDR
                    address_family = "ipv4"
                    normalized = _normalize_target(
                        resource,
                        target_type,
                    )
                else:
                    raise ValueError("type must be 'domain' or 'cidr'")
            else:
                target_type, address_family = _detect_resource(resource)

            normalized = _normalize_target(resource, target_type)
        except ValueError as exc:
            items.append(
                SmartRoutingImportItem(
                    line=line_number,
                    resource=resource,
                    target_type=None,
                    address_family=None,
                    status=SmartRoutingImportStatus.INVALID,
                    error=str(exc),
                )
            )
            continue

        key = (target_type, normalized)

        if key in seen:
            items.append(
                SmartRoutingImportItem(
                    line=line_number,
                    resource=normalized,
                    target_type=target_type,
                    address_family=address_family,
                    status=SmartRoutingImportStatus.DUPLICATE,
                )
            )
            continue

        seen.add(key)

        items.append(
            SmartRoutingImportItem(
                line=line_number,
                resource=normalized,
                target_type=target_type,
                address_family=address_family,
                status=SmartRoutingImportStatus.VALID,
            )
        )

    return items
