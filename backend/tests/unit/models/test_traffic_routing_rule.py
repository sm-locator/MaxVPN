import pytest
from backend.models.traffic_routing_rule import (
    TrafficRoute,
    TrafficRoutingRule,
    TrafficTargetType,
)


def make_domain_rule(target: str) -> TrafficRoutingRule:
    return TrafficRoutingRule(
        target_type=TrafficTargetType.DOMAIN,
        target=target,
        action=TrafficRoute.DIRECT,
        priority=100,
    )


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        ("diadoc.kontur.ru", "diadoc.kontur.ru"),
        ("Diadoc.Kontur.Ru.", "diadoc.kontur.ru"),
        ("*.kontur.ru", "kontur.ru"),
        ("www.example.ru", "www.example.ru"),
    ],
)
def test_normalize_domain_accepts_valid_hostnames(
    target: str,
    expected: str,
) -> None:
    rule = make_domain_rule(target)

    assert rule.target == expected


@pytest.mark.parametrize(
    "target",
    [
        "https://diadoc.kontur.ru/",
        "http://site.ru",
        "site.ru/path",
        "site.ru?query=1",
        "site.ru#section",
        "site.ru:443",
        "user@site.ru",
        "site..ru",
        ".site.ru",
        "-site.ru",
        "site-.ru",
        "site.ru/path/to/page",
    ],
)
def test_normalize_domain_rejects_urls_and_invalid_hostnames(
    target: str,
) -> None:
    with pytest.raises(ValueError):
        make_domain_rule(target)
