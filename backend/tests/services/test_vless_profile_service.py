from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from backend.services.vless_profile_importer import VlessProfileImporter
from backend.services.vless_profile_service import VlessProfileService
from backend.services.vpn_config_cipher import VPNConfigCipher
from cryptography.fernet import Fernet

TEST_UUID = "00000000-0000-0000-0000-000000000000"
TEST_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"

TEST_URI = (
    f"vless://{TEST_UUID}@example.com:443"
    "?encryption=none&type=tcp&security=reality"
    "&sni=example.com"
    f"&pbk={TEST_KEY}"
    "&sid=abcd&fp=firefox&flow=xtls-rprx-vision"
    "#Test%20server"
)


class FakeVlessProfileRepository:
    def __init__(self):
        self.profiles = []
        self.next_id = 1

    @property
    def profile(self):
        return self.profiles[0] if self.profiles else None

    def get_by_user(self, user_id: int):
        own = [item for item in self.profiles if item.user_id == user_id]
        return next((item for item in own if item.enabled), own[0] if own else None)

    def list_by_user(self, user_id: int):
        return [item for item in self.profiles if item.user_id == user_id]

    def get_by_id_for_user(self, user_id: int, profile_id: int):
        return next(
            (
                item
                for item in self.profiles
                if item.user_id == user_id and item.id == profile_id
            ),
            None,
        )

    def create_for_user(
        self, user_id: int, name: str, encrypted_config: str, enabled: bool = True
    ):
        profile = SimpleNamespace(
            id=self.next_id,
            user_id=user_id,
            name=name,
            encrypted_config=encrypted_config,
            enabled=enabled,
        )
        self.next_id += 1
        self.profiles.append(profile)
        return profile

    def update(self, profile):
        return profile

    def delete_for_user(self, user_id: int, profile_id: int):
        profile = self.get_by_id_for_user(user_id, profile_id)
        if profile is None:
            return False
        self.profiles.remove(profile)
        return True


@pytest.fixture
def service_and_repo():
    repo = FakeVlessProfileRepository()
    cipher = VPNConfigCipher(Fernet.generate_key().decode("ascii"))
    service = VlessProfileService(
        repository=repo,
        cipher=cipher,
        importer=VlessProfileImporter(),
    )
    return service, repo, cipher


def test_import_encrypts_config_and_public_read_hides_uuid(service_and_repo):
    service, repo, cipher = service_and_repo

    result = service.save(user_id=7, source=TEST_URI)

    assert result.name == "Test server"
    assert result.address == "example.com"
    assert result.port == 443
    assert result.security == "reality"
    assert result.flow == "xtls-rprx-vision"
    assert result.has_uuid is True

    assert repo.profile is not None
    assert TEST_UUID not in repo.profile.encrypted_config

    decrypted = cipher.decrypt(repo.profile.encrypted_config)
    assert TEST_UUID in decrypted

    assert not hasattr(result, "uuid")
    assert not hasattr(result, "public_key")


def test_profile_can_be_read_after_encrypted_roundtrip(service_and_repo):
    service, _, _ = service_and_repo

    service.save(user_id=7, source=TEST_URI)
    result = service.get(user_id=7)

    assert result is not None
    assert result.address == "example.com"
    assert result.server_name == "example.com"
    assert result.fingerprint == "firefox"


def test_saving_again_adds_another_profile(service_and_repo):
    service, repo, _ = service_and_repo

    first = service.save(user_id=7, source=TEST_URI, name="First")
    second = service.save(
        user_id=7, source=TEST_URI.replace("example.com", "example.org"), name="Second"
    )

    assert first.id != second.id
    assert second.name == "Second"
    assert len(repo.profiles) == 2
    assert repo.profiles[1].name == "Second"


def test_invalid_source_is_not_saved(service_and_repo):
    service, repo, _ = service_and_repo

    with pytest.raises(ValueError):
        service.save(user_id=7, source="not-a-vless-profile")

    assert repo.profile is None


def test_validation_rejects_json_tls_until_supported():
    importer = VlessProfileImporter()
    source = json.dumps(
        {
            "outbounds": [
                {
                    "protocol": "vless",
                    "tag": "test",
                    "settings": {
                        "vnext": [
                            {
                                "address": "example.com",
                                "port": 443,
                                "users": [{"id": TEST_UUID}],
                            }
                        ]
                    },
                    "streamSettings": {
                        "network": "tcp",
                        "security": "tls",
                        "tlsSettings": {"serverName": "example.com"},
                    },
                }
            ]
        }
    )

    with pytest.raises(ValueError, match="Unsupported VLESS stream security"):
        importer.parse(source)


def test_batch_import_saves_valid_links_and_reports_invalid_and_duplicate(
    service_and_repo,
):
    service, repo, _ = service_and_repo
    second_uri = TEST_URI.replace("example.com", "example.org")

    result = service.import_many(
        7, [TEST_URI, second_uri, TEST_URI, "not-a-vless-profile"]
    )

    assert result.imported == 2
    assert result.duplicates == 1
    assert result.failed == 1
    assert len(repo.profiles) == 2
    assert [item.status for item in result.items] == [
        "imported",
        "imported",
        "duplicate",
        "invalid",
    ]


def test_profile_limit_is_enforced(service_and_repo):
    service, _, _ = service_and_repo
    for index in range(service.MAX_PROFILES):
        service.save(7, TEST_URI.replace("example.com", f"node{index}.example.com"))

    with pytest.raises(ValueError, match="limit_reached"):
        service.save(7, TEST_URI.replace("example.com", "node-over-limit.example.com"))


def test_export_bundle_keeps_profiles_private_until_explicit_export(service_and_repo):
    service, _, _ = service_and_repo
    service.save(
        user_id=7, source=TEST_URI, name="Router migration node", enabled=False
    )

    bundle = service.export_bundle(7)

    assert bundle["format"] == "maxvpn-vless-profiles"
    assert bundle["version"] == 1
    assert len(bundle["profiles"]) == 1
    exported = bundle["profiles"][0]
    assert exported["name"] == "Router migration node"
    assert exported["enabled"] is False
    assert exported["source"].startswith("vless://")
    assert TEST_UUID in exported["source"]
    assert f"pbk={TEST_KEY}" in exported["source"]
    assert bundle["settings"] == {"urltest_interval": "3m", "urltest_tolerance_ms": 50}
    assert "Keep this file private" in bundle["warning"]


def appliance_profile(
    profile_id: int,
    *,
    address: str = "example.com",
    uuid: str = TEST_UUID,
    name: str = "Router profile",
    enabled: bool = True,
):
    return {
        "id": profile_id,
        "name": name,
        "address": address,
        "port": 443,
        "uuid": uuid,
        "flow": "xtls-rprx-vision",
        "network": "tcp",
        "enabled": enabled,
        "reality": {
            "server_name": address,
            "public_key": TEST_KEY,
            "short_id": "abcd",
            "fingerprint": "firefox",
        },
    }


def test_appliance_sync_status_detects_profile_drift(service_and_repo):
    service, _, _ = service_and_repo
    service.save(user_id=7, source=TEST_URI, name="Old local name")
    service.save(
        user_id=7,
        source=(
            "vless://11111111-1111-1111-1111-111111111111@old.example.com:443"
            "?encryption=none&type=tcp&security=none#Local%20only"
        ),
        name="Local only",
    )
    store = {
        "version": 1,
        "profiles": [
            appliance_profile(7, name="Renamed on router"),
            appliance_profile(
                21,
                address="router-only.example.net",
                uuid="22222222-2222-2222-2222-222222222222",
                name="Router only",
            ),
        ],
        "settings": {"urltest_interval": "3m", "urltest_tolerance_ms": 50},
        "selection": {"mode": "manual", "profile_id": 7},
    }

    status = service.appliance_sync_status(7, store)

    assert status["connected"] is True
    assert status["sync_required"] is True
    assert status["on_router_only"][0]["appliance_id"] == 21
    assert status["local_only"][0]["name"] == "Local only"
    assert status["updated"][0]["name"] == "Renamed on router"
    serialized = json.dumps(status)
    assert TEST_UUID not in serialized
    assert TEST_KEY not in serialized


def test_synchronize_from_appliance_reconciles_profiles_and_settings(service_and_repo):
    service, repo, _ = service_and_repo
    service.save(user_id=7, source=TEST_URI, name="Old local name")
    service.save(
        user_id=7,
        source=(
            "vless://11111111-1111-1111-1111-111111111111@old.example.com:443"
            "?encryption=none&type=tcp&security=none#Local%20only"
        ),
        name="Local only",
    )
    store = {
        "version": 1,
        "profiles": [
            appliance_profile(7, name="Renamed on router"),
            appliance_profile(
                21,
                address="router-only.example.net",
                uuid="22222222-2222-2222-2222-222222222222",
                name="Router only",
            ),
        ],
        "settings": {"urltest_interval": "3m", "urltest_tolerance_ms": 50},
        "selection": {"mode": "manual", "profile_id": 7},
    }

    result = service.synchronize_from_appliance(7, store)

    assert result == {
        "imported": 1,
        "updated": 1,
        "deleted": 1,
        "unchanged": 0,
        "profiles": 2,
        "settings_synchronized": True,
    }
    names = {profile.name for profile in service.list(7)}
    assert names == {"Renamed on router", "Router only"}
    assert len(repo.list_by_user(7)) == 2


def test_synchronize_from_appliance_refuses_empty_store_without_deleting(
    service_and_repo,
):
    service, repo, _ = service_and_repo
    service.save(user_id=7, source=TEST_URI)

    with pytest.raises(ValueError, match="пустая синхронизация отменена"):
        service.synchronize_from_appliance(
            7,
            {
                "version": 1,
                "profiles": [],
                "settings": {"urltest_interval": "3m", "urltest_tolerance_ms": 50},
            },
        )

    assert len(repo.list_by_user(7)) == 1


def test_appliance_profile_id_mapping_uses_profile_identity(service_and_repo):
    service, _, _ = service_and_repo
    profile = service.save(user_id=7, source=TEST_URI)
    store = {
        "version": 1,
        "profiles": [appliance_profile(17, name="Router profile")],
        "settings": {"urltest_interval": "3m", "urltest_tolerance_ms": 50},
    }

    assert service.appliance_profile_id_for_local_profile(7, profile.id, store) == 17
    assert (
        service.local_profile_id_for_appliance_outbound(7, store, "vless-profile-17")
        == profile.id
    )
