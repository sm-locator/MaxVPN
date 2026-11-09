from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from backend.infrastructure.openwrt.openwrt_vless_singbox_controller import (
    OpenWrtVlessSingBoxController,
)
from backend.infrastructure.openwrt.openwrt_vpn_runtime_traffic_controller import (
    OpenWrtVpnRuntimeTrafficController,
)
from backend.services.vless_profile_service import VlessProfileService
from backend.services.vless_singbox_config_renderer import (
    VlessSingBoxConfigRenderer,
)


class VlessRuntimeService:
    """
    Orchestrate sing-box configuration and process lifecycle.

    LAN routing changes are delegated to the OpenWrt runtime helpers.
    """

    def __init__(
        self,
        profile_service: VlessProfileService,
        controller: OpenWrtVlessSingBoxController,
        config_renderer: VlessSingBoxConfigRenderer | None = None,
        traffic_controller: OpenWrtVpnRuntimeTrafficController | None = None,
    ) -> None:
        self._profiles = profile_service
        self._controller = controller
        self._renderer = config_renderer or VlessSingBoxConfigRenderer()
        self._traffic_controller = traffic_controller

    def status(self, user_id: int | None = None) -> dict[str, Any]:
        current = self._controller.status()
        routing_enabled = False
        if self._traffic_controller is not None:
            routing_enabled = self._traffic_controller.get_mode() == "vless"
        runtime_info: dict[str, Any] = {}
        if current.get("running"):
            info_reader = getattr(self._controller, "runtime_server_info", None)
            if callable(info_reader):
                try:
                    value = info_reader()
                    if isinstance(value, dict):
                        runtime_info = value
                except RuntimeError:
                    runtime_info = {}
            else:
                # Compatibility for existing controller test doubles/integrations.
                selected_reader = getattr(self._controller, "selected_outbound", None)
                if callable(selected_reader):
                    try:
                        selected = selected_reader()
                        runtime_info["selected_outbound"] = selected
                        runtime_info["active_outbound"] = (
                            selected if selected and selected != "vless-auto" else None
                        )
                        runtime_info["selection_mode"] = (
                            "manual"
                            if selected and selected != "vless-auto"
                            else "auto"
                        )
                    except RuntimeError:
                        pass
        selected_outbound = runtime_info.get("selected_outbound")
        active_outbound = runtime_info.get("active_outbound")
        selection_mode = runtime_info.get("selection_mode")
        active_server_name = None
        selected_profile_id = None
        active_server_address = runtime_info.get("active_server_address")
        active_server_port = runtime_info.get("active_server_port")
        if selection_mode is None:
            selection_mode = (
                "manual"
                if selected_outbound and selected_outbound != "vless-auto"
                else "auto"
            )

        # sing-box reports the active outbound tag for multi-profile configs.
        # Resolve it against this user's saved profiles for a useful dashboard status.
        active_match = None
        if isinstance(active_outbound, str):
            match = re.fullmatch(
                r"vless-profile-([1-9][0-9]*)",
                active_outbound,
            )
            if match:
                active_match = int(match.group(1))

        list_profiles = getattr(self._profiles, "list", None)
        if user_id is not None and callable(list_profiles):
            try:
                profiles = list_profiles(user_id)
            except (LookupError, ValueError):
                profiles = []
            # Profile IDs in the localhost database can differ from the router-side
            # outbound tags after a pull sync. Prefer the actual endpoint when the
            # controller resolved it; only fall back to numeric IDs for older runtimes.
            active_profile = None
            if active_server_address is not None:
                active_profile = next(
                    (
                        item
                        for item in profiles
                        if str(getattr(item, "address", "")).strip("[]").lower()
                        == str(active_server_address).strip("[]").lower()
                        and getattr(item, "port", None) == active_server_port
                    ),
                    None,
                )
            if active_profile is None and active_match is not None:
                active_profile = next(
                    (
                        item
                        for item in profiles
                        if getattr(item, "id", None) == active_match
                    ),
                    None,
                )
            if active_profile is not None:
                if selection_mode == "manual":
                    selected_profile_id = int(getattr(active_profile, "id"))
                active_server_name = getattr(active_profile, "name", None)
                active_server_address = active_server_address or getattr(
                    active_profile,
                    "address",
                    None,
                )
                active_server_port = active_server_port or getattr(
                    active_profile,
                    "port",
                    None,
                )

        return {
            **current,
            "interface": "maxvpn0",
            "lan_routing_enabled": routing_enabled,
            "selected_outbound": selected_outbound,
            "active_outbound": active_outbound,
            "active_server_name": active_server_name,
            "active_server_address": active_server_address,
            "active_server_port": active_server_port,
            "selection_mode": selection_mode,
            "selected_profile_id": selected_profile_id,
            "runtime_config_mode": runtime_info.get("runtime_config_mode"),
            "message": (
                "sing-box runtime status only; LAN traffic routing through "
                "maxvpn0 has not been configured"
                if self._traffic_controller is None
                else (
                    "VLESS LAN routing is active"
                    if routing_enabled
                    else (
                        "sing-box runtime is available; LAN traffic is not routed "
                        "through VLESS"
                    )
                )
            ),
        }

    def get_selection_history(self, user_id: int | None = None) -> dict[str, Any]:
        """Return router history plus a best-effort router-tag -> local-profile ID map.

        The journal's ``vless-profile-N`` tags use appliance-side IDs. Those IDs
        can differ from the localhost database IDs after a profile sync, so the
        raw journal remains untouched and the explicit mapping is returned
        separately for the UI.
        """
        reader = getattr(self._controller, "selection_history", None)
        if not callable(reader):
            raise RuntimeError("vless_selection_history_unavailable")
        raw_history = reader()
        if not isinstance(raw_history, dict):
            return raw_history

        outbound_tags: set[str] = set()

        def add_outbound(value: Any) -> None:
            if isinstance(value, str) and re.fullmatch(
                r"vless-profile-[1-9][0-9]*", value
            ):
                outbound_tags.add(value)

        current = raw_history.get("current")
        if isinstance(current, dict):
            add_outbound(current.get("active_outbound"))
            add_outbound(current.get("selected_outbound"))
            delays = current.get("profile_delays")
            if isinstance(delays, dict):
                for outbound in delays:
                    add_outbound(outbound)

        events = raw_history.get("events")
        if isinstance(events, list):
            for event in events:
                if isinstance(event, dict):
                    add_outbound(event.get("previous_outbound"))
                    add_outbound(event.get("active_outbound"))

        profile_id_map: dict[str, int] = {}
        store_reader = getattr(self._controller, "read_appliance_vless_store", None)
        id_mapper = getattr(
            self._profiles, "local_profile_id_for_appliance_outbound", None
        )
        if (
            user_id is not None
            and outbound_tags
            and callable(store_reader)
            and callable(id_mapper)
        ):
            try:
                store = store_reader()
            except Exception:
                # The journal is still useful if the optional profile-store read
                # fails; return an empty map rather than failing the whole endpoint.
                store = None
            if isinstance(store, dict):
                for outbound in sorted(outbound_tags):
                    try:
                        local_id = id_mapper(user_id, store, outbound)
                    except (LookupError, RuntimeError, ValueError):
                        continue
                    if local_id is not None:
                        profile_id_map[outbound] = int(local_id)

        history = dict(raw_history)
        history["profile_id_map"] = profile_id_map
        return history

    def appliance_sync_status(self, user_id: int) -> dict[str, Any]:
        """Return router/local drift and compare saved selection
        with the live selector."""
        store_reader = getattr(self._controller, "read_appliance_vless_store", None)
        diff_reader = getattr(self._profiles, "appliance_sync_status", None)
        if not callable(store_reader) or not callable(diff_reader):
            raise RuntimeError("VLESS appliance sync is not available")
        store = store_reader()
        diff = diff_reader(user_id, store)
        runtime = self.status(user_id)

        selection = (
            store.get("selection") if isinstance(store.get("selection"), dict) else {}
        )
        requested_mode = selection.get("mode")
        try:
            requested_profile_id = int(selection.get("profile_id"))
        except (TypeError, ValueError):
            requested_profile_id = None
        enabled_ids = {
            int(row.get("id", -1))
            for row in store.get("profiles", [])
            if isinstance(row, dict) and row.get("enabled")
        }
        if requested_mode == "manual" and requested_profile_id in enabled_ids:
            mode = "manual"
            desired_outbound = f"vless-profile-{requested_profile_id}"
            desired_profile_id = requested_profile_id
        else:
            mode = "auto"
            desired_outbound = "vless-auto"
            desired_profile_id = None

        runtime_selected_outbound = runtime.get("selected_outbound")
        running = bool(runtime.get("running"))
        if not running:
            runtime_mode = "unknown"
        elif runtime_selected_outbound == "vless-auto":
            runtime_mode = "auto"
        elif isinstance(runtime_selected_outbound, str) and re.fullmatch(
            r"vless-profile-[1-9][0-9]*", runtime_selected_outbound
        ):
            runtime_mode = "manual"
        else:
            runtime_mode = "unknown"
        selection_pending = bool(store.get("profiles")) and (
            not running or runtime_selected_outbound != desired_outbound
        )

        selected_row = (
            next(
                (
                    row
                    for row in store.get("profiles", [])
                    if isinstance(row, dict)
                    and int(row.get("id", -1)) == desired_profile_id
                ),
                None,
            )
            if desired_profile_id is not None
            else None
        )
        if mode == "manual" and isinstance(selected_row, dict):
            address = str(selected_row.get("address") or "").strip("[]").lower()
            port = selected_row.get("port")
            signature = f"manual:{address}:{port}"
            selected_name = str(selected_row.get("name") or f"{address}:{port}")
        else:
            signature = "auto"
            selected_name = None

        return {
            **diff,
            "kill_switch_enabled": (
                (store.get("settings") or {}).get("wan_fallback_enabled") is not True
            ),
            # selection_mode/signature describe the saved router-side intent. Runtime
            # fields below separately describe what the live sing-box process uses.
            "selection_mode": mode,
            "selected_profile": selected_name,
            "selection_signature": signature,
            "selection_pending": selection_pending,
            "desired_outbound": desired_outbound,
            "runtime_selection_mode": runtime_mode,
            "runtime_selected_outbound": runtime_selected_outbound,
            "runtime_active_outbound": runtime.get("active_outbound"),
            "checked_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }

    def set_appliance_kill_switch(self, enabled: bool) -> dict[str, Any]:
        """Set the router-wide Kill Switch policy without restarting sing-box."""
        setter = getattr(self._controller, "set_wan_fallback_enabled", None)
        if not callable(setter):
            raise RuntimeError("VLESS Kill Switch control is not available")
        return setter(not enabled)

    def synchronize_from_appliance(
        self,
        user_id: int,
        *,
        confirm_delete_local_only: bool = False,
    ) -> dict[str, Any]:
        """Pull profiles/settings from the router into localhost without applying them.

        The delete confirmation is checked against a fresh router-side snapshot so a
        stale browser diff cannot accidentally delete localhost-only profiles.
        """
        store_reader = getattr(self._controller, "read_appliance_vless_store", None)
        sync_writer = getattr(self._profiles, "synchronize_from_appliance", None)
        diff_reader = getattr(self._profiles, "appliance_sync_status", None)
        if (
            not callable(store_reader)
            or not callable(sync_writer)
            or not callable(diff_reader)
        ):
            raise RuntimeError("VLESS appliance sync is not available")
        store = store_reader()
        diff = diff_reader(user_id, store)
        local_only = diff.get("local_only", [])
        if local_only and not confirm_delete_local_only:
            raise ValueError(
                f"На localhost:8080 есть {len(local_only)} профиль(я), "
                "которых нет на maxvpn.lan. "
                "Подтвердите удаление этих локальных профилей "
                "и повторите синхронизацию."
            )
        result = sync_writer(user_id, store)
        status = self.appliance_sync_status(user_id)
        return {**status, "synced": True, "sync_result": result}

    def enable_lan_routing(self, user_id: int) -> dict[str, Any]:
        # Validate the saved profile and confirm the process before touching routes.
        self._build_config(user_id)
        current = self._controller.status()
        if not current.get("running"):
            raise RuntimeError("vless_runtime_not_running")
        if self._traffic_controller is None:
            raise RuntimeError("VLESS LAN traffic controller is not configured")

        watchdog_warning = self._traffic_controller.enable_vless_mode()
        final = self.status(user_id)
        if not final["lan_routing_enabled"]:
            raise RuntimeError("vless_lan_routing_verification_failed")

        message = (
            "VLESS LAN routing enabled; IPv4 DIRECT exceptions are retained "
            "and LAN IPv6 forwarding is blocked in VLESS mode"
        )
        if watchdog_warning:
            message += (
                ". WARNING: LAN routing is active, but the VLESS watchdog did not "
                "start; automatic runtime recovery is unavailable until it is "
                "started. The watchdog remains enabled for router boot. "
                f"Details: {watchdog_warning}"
            )

        return {
            **final,
            "action": "lan-routing-enabled",
            "message": message,
        }

    def prepare(self, user_id: int) -> dict[str, Any]:
        config = self._build_config(user_id)

        current = self._controller.status()
        if current["running"]:
            raise RuntimeError(
                "sing-box is running; stop it before preparing a new config"
            )

        self._install(config)
        return {
            **self.status(user_id),
            "action": "prepared",
            "prepared": True,
            "message": (
                "Binary, service and configuration prepared; "
                "sing-box has not been started and LAN routes were not changed"
            ),
        }

    def start(self, user_id: int) -> dict[str, Any]:
        # Validate the profile before stopping or changing a running process.
        config = self._build_config(user_id)
        current = self._controller.status()
        was_running = bool(current.get("running"))

        backup_reader = getattr(self._controller, "backup_config", None)
        restore_config = getattr(self._controller, "restore_config", None)
        discard_backup = getattr(self._controller, "discard_config_backup", None)
        backup_path = backup_reader() if callable(backup_reader) else None

        try:
            if was_running:
                self._controller.stop()

            self._install(config)
            self._controller.start()
            after_start = self._controller.status()
            if not after_start.get("running"):
                raise RuntimeError(
                    "sing-box apply failed: service did not remain running after start"
                )
        except Exception as apply_error:
            if callable(restore_config):
                try:
                    # Stop a failed/partially started instance before restoring.
                    failed_state = self._controller.status()
                    if failed_state.get("running"):
                        self._controller.stop()
                    restore_config(backup_path)
                    if was_running:
                        self._controller.start()
                        restored_state = self._controller.status()
                        if not restored_state.get("running"):
                            raise RuntimeError(
                                "previous sing-box config was restored, but "
                                "the service did not restart"
                            )
                except Exception as rollback_error:
                    raise RuntimeError(
                        f"sing-box apply failed: {apply_error}; "
                        f"rollback failed: {rollback_error}. "
                        "The router config backup was retained when possible."
                    ) from apply_error
            raise
        else:
            if callable(discard_backup):
                discard_backup(backup_path)

        return {
            **self.status(user_id),
            "action": "started",
            "prepared": True,
            "message": (
                "sing-box started and checked; existing LAN routing mode and "
                "DIRECT rules were not changed"
            ),
        }

    def stop(self, user_id: int | None = None) -> dict[str, Any]:
        message = "sing-box stop requested"
        if self._traffic_controller is not None:
            if self._controller.stop_with_lan_fallback():
                message += (
                    "; active VLESS LAN routing was returned to WAN before stopping"
                )
        else:
            current = self._controller.status()
            if current["running"]:
                self._controller.stop()
            if current["installed"]:
                self._controller.disable_autostart()

        final = self.status(user_id)
        if final["running"]:
            raise RuntimeError("sing-box still reports running after stop")

        return {
            **final,
            "action": "stopped",
            "prepared": bool(final["installed"]),
            "message": message,
        }

    def _build_config(self, user_id: int) -> dict[str, Any]:
        list_enabled = getattr(self._profiles, "get_enabled_servers", None)
        if callable(list_enabled):
            profiles = list_enabled(user_id)
        else:
            # Compatibility for older test doubles and integrations.
            profile = self._profiles.get(user_id)
            if profile is None:
                raise LookupError("vless_profile_not_found")
            if not profile.enabled:
                raise ValueError("vless_profile_disabled")
            server = self._profiles.get_server(user_id)
            profiles = (
                [(getattr(profile, "id", 1), server)] if server is not None else []
            )

        if not profiles:
            profile = self._profiles.get(user_id)
            if profile is None:
                raise LookupError("vless_profile_not_found")
            raise ValueError("vless_profile_disabled")
        get_settings = getattr(self._profiles, "get_runtime_settings", None)
        settings = (
            get_settings(user_id)
            if callable(get_settings)
            else {
                "urltest_interval": "3m",
                "urltest_tolerance_ms": 50,
            }
        )
        return self._renderer.render_profiles(
            profiles,
            interval=settings.get("urltest_interval", "3m"),
            tolerance_ms=int(settings.get("urltest_tolerance_ms", 50)),
        )

    def select_outbound(self, user_id: int, profile_id: int | None) -> dict[str, Any]:
        current = self._controller.status()
        if not current.get("running"):
            raise RuntimeError("sing-box_runtime_not_running")
        selector = getattr(self._controller, "select_outbound", None)
        selected_reader = getattr(self._controller, "selected_outbound", None)
        if not callable(selector) or not callable(selected_reader):
            raise RuntimeError("sing-box outbound selection API is not available")

        if profile_id is None:
            tag = "vless-auto"
        else:
            profile = self._profiles.get_profile(user_id, profile_id)
            if profile is None:
                raise LookupError("vless_profile_not_found")
            if not profile.enabled:
                raise ValueError("Cannot select a disabled VLESS profile")
            tag_id = int(profile.id)
            store_reader = getattr(self._controller, "read_appliance_vless_store", None)
            id_mapper = getattr(
                self._profiles, "appliance_profile_id_for_local_profile", None
            )
            if callable(store_reader) and callable(id_mapper):
                store = store_reader()
                appliance_id = id_mapper(user_id, profile_id, store)
                if appliance_id is None:
                    raise ValueError(
                        "Профиль отсутствует на maxvpn.lan. "
                        "Сначала синхронизируйте список VLESS-серверов."
                    )
                tag_id = int(appliance_id)
            tag = f"vless-profile-{tag_id}"

        selector(tag)
        final = self.status(user_id)
        return {
            **final,
            "selected_outbound": selected_reader(),
            "selection_mode": "auto" if tag == "vless-auto" else "manual",
            "action": "outbound-selected",
            "message": (
                "Automatic server selection enabled"
                if tag == "vless-auto"
                else "Manual VLESS server selected"
            ),
        }

    def test_profile_delays(self, user_id: int) -> dict[str, Any]:
        if not self._controller.status().get("running"):
            raise RuntimeError("sing-box_runtime_not_running")
        list_enabled = getattr(self._profiles, "get_enabled_servers", None)
        if not callable(list_enabled):
            raise RuntimeError("VLESS profile list is not supported by this service")
        profiles = list_enabled(user_id)
        if not profiles:
            raise LookupError("vless_profile_not_found")
        delay_reader = getattr(self._controller, "test_outbound_delays", None)
        if not callable(delay_reader):
            raise RuntimeError("sing-box delay test API is not available")
        tag_by_local_id: dict[int, int] = {}
        store_reader = getattr(self._controller, "read_appliance_vless_store", None)
        id_mapper = getattr(
            self._profiles, "appliance_profile_id_for_local_profile", None
        )
        if callable(store_reader) and callable(id_mapper):
            store = store_reader()
            for profile_id, _ in profiles:
                mapped = id_mapper(user_id, profile_id, store)
                if mapped is not None:
                    tag_by_local_id[profile_id] = int(mapped)
        else:
            tag_by_local_id = {profile_id: profile_id for profile_id, _ in profiles}
        tags = [
            f"vless-profile-{appliance_id}"
            for appliance_id in sorted(set(tag_by_local_id.values()))
        ]
        measured = delay_reader(tags) if tags else {}
        recorder = getattr(self._profiles, "record_delay_results", None)
        if not callable(recorder):
            raise RuntimeError("VLESS profile availability history is not available")
        measurements = {
            profile_id: (
                measured.get(f"vless-profile-{tag_by_local_id[profile_id]}")
                if profile_id in tag_by_local_id
                else None
            )
            for profile_id, _ in profiles
        }
        return {"results": recorder(user_id, measurements)}

    def get_profile_delay_history(self, user_id: int) -> dict[str, Any]:
        reader = getattr(self._profiles, "get_delay_history", None)
        if not callable(reader):
            raise RuntimeError("VLESS profile availability history is not available")
        return {"results": reader(user_id)}

    def _install(self, config: dict[str, Any]) -> None:
        # The controller validates the binary version, refuses to overwrite
        # an unknown existing binary/service, and checks the config before
        # atomically installing it with owner-only permissions.
        self._controller.install_verified_binary()
        self._controller.install_service_script()
        self._controller.install_config(config)
