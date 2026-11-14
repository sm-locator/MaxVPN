from pathlib import Path

from backend.services.smart_routing_import import (
    SmartRoutingImportStatus,
    SmartRoutingImportType,
    parse_txt_import,
)


def test_parse_txt_import_detects_domains_ipv4_and_cidr() -> None:
    content = """\
example.com
192.168.1.10
192.168.1.0/24
"""

    items = parse_txt_import(content)

    assert len(items) == 3

    assert items[0].resource == "example.com"
    assert items[0].target_type is SmartRoutingImportType.DOMAIN
    assert items[0].address_family == "any"
    assert items[0].status is SmartRoutingImportStatus.VALID

    assert items[1].resource == "192.168.1.10"
    assert items[1].target_type is SmartRoutingImportType.CIDR
    assert items[1].address_family == "ipv4"
    assert items[1].status is SmartRoutingImportStatus.VALID

    assert items[2].resource == "192.168.1.0/24"
    assert items[2].target_type is SmartRoutingImportType.CIDR
    assert items[2].address_family == "ipv4"
    assert items[2].status is SmartRoutingImportStatus.VALID


def test_parse_txt_import_detects_duplicates_after_normalization() -> None:
    content = """\
example.com
EXAMPLE.COM.
192.168.1.0/24
192.168.1.12/24
"""

    items = parse_txt_import(content)

    assert items[0].status is SmartRoutingImportStatus.VALID
    assert items[1].status is SmartRoutingImportStatus.DUPLICATE

    assert items[2].resource == "192.168.1.0/24"
    assert items[2].status is SmartRoutingImportStatus.VALID

    assert items[3].resource == "192.168.1.0/24"
    assert items[3].status is SmartRoutingImportStatus.DUPLICATE


def test_parse_txt_import_rejects_invalid_targets_and_ipv6() -> None:
    content = """\
https://example.com/
example.com/path
2001:db8::1
2001:db8::/32
"""

    items = parse_txt_import(content)

    assert len(items) == 4
    assert all(item.status is SmartRoutingImportStatus.INVALID for item in items)

    assert items[2].error == "IPv6 is not supported"
    assert items[3].error == "IPv6 is not supported"


def test_parse_txt_import_ignores_empty_lines_and_comments() -> None:
    content = """\
# comment

example.com

   # another comment
192.168.1.1
"""

    items = parse_txt_import(content)

    assert len(items) == 2
    assert items[0].resource == "example.com"
    assert items[1].resource == "192.168.1.1"


def test_russia_direct_file_contains_37_valid_unique_domains() -> None:
    path = (
        Path(__file__).resolve().parents[3]
        / "data"
        / "smart-routing"
        / "russia-direct.txt"
    )

    items = parse_txt_import(path.read_text(encoding="utf-8"))

    assert len(items) == 37
    assert all(item.status is SmartRoutingImportStatus.VALID for item in items)
    assert all(item.target_type is SmartRoutingImportType.DOMAIN for item in items)
    assert all(item.address_family == "any" for item in items)

    domains = [item.resource for item in items]
    assert len(domains) == len(set(domains))


def test_parse_csv_import_with_explicit_types() -> None:
    from backend.services.smart_routing_import import parse_csv_import

    content = """\
resource,type
Example.COM.,domain
192.168.1.10,cidr
192.168.10.12/24,cidr
"""

    items = parse_csv_import(content)

    assert len(items) == 3

    assert items[0].resource == "example.com"
    assert items[0].target_type is SmartRoutingImportType.DOMAIN
    assert items[0].address_family == "any"
    assert items[0].status is SmartRoutingImportStatus.VALID

    assert items[1].resource == "192.168.1.10"
    assert items[1].target_type is SmartRoutingImportType.CIDR
    assert items[1].address_family == "ipv4"
    assert items[1].status is SmartRoutingImportStatus.VALID

    assert items[2].resource == "192.168.10.0/24"
    assert items[2].target_type is SmartRoutingImportType.CIDR
    assert items[2].address_family == "ipv4"
    assert items[2].status is SmartRoutingImportStatus.VALID


def test_parse_csv_import_without_type_uses_auto_detection() -> None:
    from backend.services.smart_routing_import import parse_csv_import

    content = """\
resource
example.com
192.168.1.10
192.168.10.0/24
"""

    items = parse_csv_import(content)

    assert len(items) == 3
    assert items[0].target_type is SmartRoutingImportType.DOMAIN
    assert items[1].target_type is SmartRoutingImportType.CIDR
    assert items[2].target_type is SmartRoutingImportType.CIDR


def test_parse_csv_import_rejects_invalid_type() -> None:
    from backend.services.smart_routing_import import parse_csv_import

    content = """\
resource,type
example.com,url
"""

    items = parse_csv_import(content)

    assert len(items) == 1
    assert items[0].status is SmartRoutingImportStatus.INVALID
    assert items[0].error == "type must be 'domain' or 'cidr'"


def test_parse_csv_import_rejects_ipv6() -> None:
    from backend.services.smart_routing_import import parse_csv_import

    content = """\
resource
2001:db8::1
2001:db8::/32
"""

    items = parse_csv_import(content)

    assert len(items) == 2
    assert all(item.status is SmartRoutingImportStatus.INVALID for item in items)
    assert all(item.error == "IPv6 is not supported" for item in items)
