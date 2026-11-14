from __future__ import annotations

from backend.services.vless_runtime_service import VlessRuntimeService


class FakeHistoryController:
    def __init__(self) -> None:
        self.history = {
            "monitor": {"enabled": True, "interval_seconds": 15},
            "current": {
                "selection_mode": "auto",
                "selected_outbound": "vless-auto",
                "active_outbound": "vless-profile-17",
                "profile_delays": {
                    "vless-profile-17": {"delay_ms": 300},
                    "vless-profile-2": {"delay_ms": 350},
                },
            },
            "events": [
                {
                    "previous_outbound": "vless-profile-2",
                    "active_outbound": "vless-profile-17",
                }
            ],
        }

    def selection_history(self):
        return self.history

    def read_appliance_vless_store(self):
        return {"version": 1, "profiles": []}


class FakeHistoryProfileService:
    def local_profile_id_for_appliance_outbound(self, user_id, store, outbound):
        assert user_id == 7
        assert store["version"] == 1
        return {"vless-profile-17": 4, "vless-profile-2": 9}.get(outbound)


def test_selection_history_maps_appliance_outbound_tags_to_local_profile_ids():
    controller = FakeHistoryController()
    service = VlessRuntimeService(FakeHistoryProfileService(), controller)

    result = service.get_selection_history(user_id=7)

    assert result["profile_id_map"] == {
        "vless-profile-17": 4,
        "vless-profile-2": 9,
    }
    # Preserve raw appliance tags and measurements for diagnostics and auditability.
    assert result["current"]["active_outbound"] == "vless-profile-17"
    assert result["current"]["profile_delays"]["vless-profile-17"]["delay_ms"] == 300
    assert result["events"][0]["previous_outbound"] == "vless-profile-2"
