from pathlib import Path

from backend.models.command_result import CommandResult
from backend.models.smart_routing_rule_data import SmartRoutingRuleData
from backend.ports.remote_command_executor import RemoteCommandExecutor
from backend.services.smart_routing_sync import (
    SmartRoutingSyncError,
    SmartRoutingSyncService,
)


class FakeExecutor(RemoteCommandExecutor):
    def __init__(self, result: CommandResult) -> None:
        self.result = result
        self.commands: list[list[str]] = []

    def run(
        self,
        command: list[str],
        stdin: str | None = None,
    ) -> CommandResult:
        self.commands.append(command)
        return self.result


def rule(
    target: str,
    *,
    target_type: str = "domain",
    priority: int = 1,
    action: str = "direct",
    address_family: str = "any",
    enabled: bool = True,
) -> SmartRoutingRuleData:
    return SmartRoutingRuleData(
        target_type=target_type,
        target=target,
        action=action,
        priority=priority,
        address_family=address_family,
        enabled=enabled,
    )


def preset_file(tmp_path: Path) -> Path:
    path = tmp_path / "russia-direct.txt"
    path.write_text(
        "gosuslugi.ru\nvkvideo.ru\n5ka.ru\n",
        encoding="utf-8",
    )
    return path


def remote_payload(rules: list[dict]) -> str:
    import json

    return json.dumps(
        {
            "rules": rules,
            "runtime": {},
        }
    )


def remote_rule(
    target: str,
    *,
    target_type: str = "domain",
    priority: int = 380,
    action: str = "direct",
    address_family: str = "any",
    enabled: bool = True,
    comment: str = "",
) -> dict:
    return {
        "target_type": target_type,
        "target": target,
        "action": action,
        "priority": priority,
        "address_family": address_family,
        "enabled": enabled,
        "comment": comment,
    }


def service(
    tmp_path: Path,
    remote_rules: list[dict],
) -> SmartRoutingSyncService:
    executor = FakeExecutor(
        CommandResult(
            stdout=remote_payload(remote_rules),
            stderr="",
            returncode=0,
        )
    )

    return SmartRoutingSyncService(
        executor=executor,
        russian_direct_file=preset_file(tmp_path),
    )


def test_preview_ignores_absolute_priority(
    tmp_path: Path,
) -> None:
    sync = service(
        tmp_path,
        [
            remote_rule("gosuslugi.ru", priority=380),
            remote_rule("example.ru", priority=370),
        ],
    )

    result = sync.preview(
        [
            rule("gosuslugi.ru", priority=1),
            rule("example.ru", priority=2300),
        ]
    )

    assert len(result.same) == 2
    assert result.semantic_mismatches == []
    assert result.order_mismatches == []


def test_preview_reports_remote_only(
    tmp_path: Path,
) -> None:
    sync = service(
        tmp_path,
        [
            remote_rule("example.ru", priority=380),
            remote_rule("vkvideo.ru", priority=370),
        ],
    )

    result = sync.preview(
        [
            rule("example.ru", priority=1),
        ]
    )

    assert len(result.remote_only) == 1
    assert result.remote_only[0]["target"] == "vkvideo.ru"


def test_preview_marks_static_and_diagnostic_rules_as_protected(
    tmp_path: Path,
) -> None:
    sync = service(
        tmp_path,
        [],
    )

    result = sync.preview(
        [
            rule(
                "31.25.243.222/32",
                target_type="cidr",
                priority=100,
                address_family="ipv4",
            ),
            rule("photo.2gis.com", priority=3302),
            rule("yandex.net", priority=3303),
        ],
        protected_local_keys={
            ("domain", "photo.2gis.com"),
            ("domain", "yandex.net"),
        },
    )

    assert len(result.protected_local_only) == 3
    assert result.unprotected_local_only == []


def test_preview_reports_semantic_mismatch(
    tmp_path: Path,
) -> None:
    sync = service(
        tmp_path,
        [
            remote_rule(
                "example.ru",
                priority=20,
                enabled=True,
            )
        ],
    )

    result = sync.preview(
        [
            rule(
                "example.ru",
                priority=2300,
                enabled=False,
            )
        ]
    )

    assert result.same == []
    assert len(result.semantic_mismatches) == 1
    assert result.semantic_mismatches[0]["target"] == "example.ru"


def test_pull_priority_allocation_preserves_russian_order(
    tmp_path: Path,
) -> None:
    sync = service(
        tmp_path,
        [
            remote_rule("gosuslugi.ru", priority=380),
            remote_rule("vkvideo.ru", priority=370),
            remote_rule("5ka.ru", priority=360),
            remote_rule(
                "gps.navy",
                priority=20,
            ),
        ],
    )

    local = [
        rule("gosuslugi.ru", priority=1),
        rule("other.ru", priority=2300),
    ]

    result = sync.preview(local)

    imports = sync.allocate_local_priorities(
        local,
        result.remote_only,
    )

    assert [(item["target"], item["local_priority"]) for item in imports] == [
        ("vkvideo.ru", 2),
        ("5ka.ru", 3),
        ("gps.navy", 2310),
    ]


def test_pull_rejects_ipv6_cidr(
    tmp_path: Path,
) -> None:
    sync = service(
        tmp_path,
        [
            remote_rule(
                "2001:db8::/64",
                target_type="cidr",
                priority=10,
                address_family="ipv6",
            )
        ],
    )

    with __import__("pytest").raises(
        SmartRoutingSyncError,
        match="ipv6_cidr_pull_not_supported",
    ):
        sync.build_pull_plan(
            [
                rule(
                    "example.ru",
                    priority=1,
                )
            ]
        )


def test_fetch_remote_state_raises_on_ssh_failure(
    tmp_path: Path,
) -> None:
    executor = FakeExecutor(
        CommandResult(
            stdout="",
            stderr="connection failed",
            returncode=255,
        )
    )

    sync = SmartRoutingSyncService(
        executor=executor,
        russian_direct_file=preset_file(tmp_path),
    )

    with __import__("pytest").raises(
        SmartRoutingSyncError,
        match="brume_routing_read_failed",
    ):
        sync.fetch_remote_state()


def test_fetch_remote_state_raises_on_invalid_json(
    tmp_path: Path,
) -> None:
    executor = FakeExecutor(
        CommandResult(
            stdout="{invalid",
            stderr="",
            returncode=0,
        )
    )

    sync = SmartRoutingSyncService(
        executor=executor,
        russian_direct_file=preset_file(tmp_path),
    )

    with __import__("pytest").raises(
        SmartRoutingSyncError,
        match="brume_routing_invalid_json",
    ):
        sync.fetch_remote_state()


class PushExecutor(RemoteCommandExecutor):
    def __init__(self, initial_rules: list[dict]) -> None:
        self.rules = [dict(rule) for rule in initial_rules]
        self.calls: list[tuple[list[str], str | None]] = []

    def run(
        self,
        command: list[str],
        stdin: str | None = None,
    ) -> CommandResult:
        self.calls.append((command, stdin))

        if command == [
            "curl",
            "-fsS",
            SmartRoutingSyncService.REMOTE_URL,
        ]:
            return CommandResult(
                stdout=remote_payload(self.rules),
                stderr="",
                returncode=0,
            )

        if "-X" in command and "POST" in command:
            import json

            payload = json.loads(stdin or "{}")

            next_id = len(self.rules) + 1
            created = {
                "id": next_id,
                "target_type": payload["target_type"],
                "target": payload["target"],
                "action": "direct",
                "priority": 430 + (next_id - 1) * 10,
                "address_family": (
                    "ipv4" if payload["target_type"] == "cidr" else "any"
                ),
                "enabled": True,
            }

            self.rules.append(created)

            return CommandResult(
                stdout=json.dumps(created),
                stderr="",
                returncode=0,
            )

        raise AssertionError(f"Unexpected command: {command!r}")


def test_preview_preserves_diagnostic_comment_for_pull(
    tmp_path: Path,
) -> None:
    sync = service(
        tmp_path,
        [
            remote_rule(
                "api.photo.2gis.com",
                comment="Диагностика: 2gis.ru",
            )
        ],
    )

    result = sync.preview([])

    assert result.remote_only[0]["comment"] == "Диагностика: 2gis.ru"


def test_remote_comment_does_not_change_fingerprint(
    tmp_path: Path,
) -> None:
    sync_a = service(
        tmp_path,
        [remote_rule("api.photo.2gis.com", comment="Диагностика: 2gis.ru")],
    )
    sync_b = service(
        tmp_path,
        [remote_rule("api.photo.2gis.com", comment="")],
    )

    assert (
        sync_a.fetch_remote_state()["fingerprint"]
        == sync_b.fetch_remote_state()["fingerprint"]
    )


def test_preview_detects_existing_diagnostic_rule_without_group_link(
    tmp_path: Path,
) -> None:
    sync = service(
        tmp_path,
        [
            remote_rule(
                "api.photo.2gis.com",
                comment="Диагностика: 2gis.ru",
            )
        ],
    )

    result = sync.preview(
        [
            rule(
                "api.photo.2gis.com",
                priority=100,
            )
        ]
    )

    assert result.remote_only == []
    assert len(result.diagnostic_relinks) == 1
    assert result.diagnostic_relinks[0]["target"] == "api.photo.2gis.com"


def test_push_local_only_adds_rules_to_brume(
    tmp_path: Path,
) -> None:
    executor = PushExecutor(
        [
            remote_rule(
                "example.ru",
                priority=420,
            )
        ]
    )

    sync = SmartRoutingSyncService(
        executor=executor,
        russian_direct_file=preset_file(tmp_path),
    )

    result = sync.push_local_only(
        [
            rule(
                "31.25.243.222/32",
                target_type="cidr",
                priority=100,
                address_family="ipv4",
            )
        ]
    )

    assert result["pushed"] is True
    assert result["created_count"] == 1
    assert result["created"][0]["target"] == "31.25.243.222/32"
    assert result["apply_required"] is True

    post_calls = [
        (command, stdin)
        for command, stdin in executor.calls
        if "-X" in command and "POST" in command
    ]

    assert len(post_calls) == 1
    assert "31.25.243.222/32" in (post_calls[0][1] or "")


def test_push_rejects_ipv6_cidr(
    tmp_path: Path,
) -> None:
    executor = PushExecutor([])

    sync = SmartRoutingSyncService(
        executor=executor,
        russian_direct_file=preset_file(tmp_path),
    )

    import pytest

    with pytest.raises(
        SmartRoutingSyncError,
        match="ipv6_cidr_push_not_supported",
    ):
        sync.push_local_only(
            [
                rule(
                    "2001:db8::/64",
                    target_type="cidr",
                    priority=100,
                    address_family="ipv6",
                )
            ]
        )


def test_push_rejects_disabled_rule(
    tmp_path: Path,
) -> None:
    executor = PushExecutor([])

    sync = SmartRoutingSyncService(
        executor=executor,
        russian_direct_file=preset_file(tmp_path),
    )

    import pytest

    with pytest.raises(
        SmartRoutingSyncError,
        match="disabled_push_not_supported",
    ):
        sync.push_local_only(
            [
                rule(
                    "disabled.example.ru",
                    priority=100,
                    enabled=False,
                )
            ]
        )


def test_preview_normalizes_host_cidr_to_slash_32(
    tmp_path: Path,
) -> None:
    sync = service(
        tmp_path,
        [
            remote_rule(
                "31.25.243.222/32",
                target_type="cidr",
                priority=10,
                address_family="ipv4",
            )
        ],
    )

    result = sync.preview(
        [
            rule(
                "31.25.243.222",
                target_type="cidr",
                priority=100,
                address_family="ipv4",
            )
        ]
    )

    assert len(result.same) == 1
    assert result.local_only == []
    assert result.remote_only == []
    assert result.semantic_mismatches == []
    assert result.order_mismatches == []


def test_preview_ignores_domain_cidr_order_difference(
    tmp_path: Path,
) -> None:
    sync = service(
        tmp_path,
        [
            remote_rule(
                "gosuslugi.ru",
                priority=380,
            ),
            remote_rule(
                "vkvideo.ru",
                priority=390,
            ),
            remote_rule(
                "31.25.243.222/32",
                target_type="cidr",
                priority=1040,
                address_family="ipv4",
            ),
            remote_rule(
                "81.90.182.109/32",
                target_type="cidr",
                priority=1050,
                address_family="ipv4",
            ),
        ],
    )

    result = sync.preview(
        [
            rule(
                "31.25.243.222",
                target_type="cidr",
                priority=100,
                address_family="ipv4",
            ),
            rule(
                "81.90.182.109",
                target_type="cidr",
                priority=500,
                address_family="ipv4",
            ),
            rule(
                "gosuslugi.ru",
                priority=1,
            ),
            rule(
                "vkvideo.ru",
                priority=2,
            ),
        ]
    )

    assert len(result.same) == 4
    assert result.local_only == []
    assert result.remote_only == []
    assert result.semantic_mismatches == []
    assert result.order_mismatches == []
