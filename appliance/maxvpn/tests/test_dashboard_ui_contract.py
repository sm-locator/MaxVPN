from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[3]
SOURCE_HTML = ROOT / "appliance" / "maxvpn" / "index.html"


def test_dashboard_metrics_are_protocol_aware():
    html = SOURCE_HTML.read_text(encoding="utf-8")
    for required in (
        'id="ovMetric2Label"',
        'id="ovMetric3Label"',
        'id="ovMetric4Label"',
        'id="vpnDetailsTitle"',
        "mode==='vless'",
        "mode==='vpn'",
        "mode==='wan'",
        "Активные DIRECT-правила Smart Routing направляют совпадающие ресурсы напрямую через WAN",
        "Статистика трафика",
    ):
        assert required in html


def test_mode_copy_does_not_claim_all_lan_traffic_uses_vless():
    html = SOURCE_HTML.read_text(encoding="utf-8")
    assert "Весь LAN направляется через VLESS" not in html
    assert "Весь LAN направляется через AmneziaWG" not in html


def test_vless_renderer_defines_its_own_route_health_and_direct_notice():
    html = SOURCE_HTML.read_text(encoding="utf-8")
    start = html.index("function renderVless(){")
    end = html.index("function renderVlessProfiles(){", start)
    renderer = html[start:end]
    assert "const routeHealthy=mode==='vless'&&v.lan_route_healthy===true;" in renderer
    assert "const directNotice=state.dirty" in renderer


def test_vless_renderer_uses_its_local_state_not_render_scope_variable():
    html = SOURCE_HTML.read_text(encoding="utf-8")
    start = html.index("function renderVless(){")
    end = html.index("function renderVlessProfiles(){", start)
    renderer = html[start:end]
    assert "v.lan_route_healthy" in renderer
    assert "vl.lan_route_healthy" not in renderer


def test_overview_uses_vless_tun_interface_not_amneziawg_interface():
    html = SOURCE_HTML.read_text(encoding="utf-8")
    assert "row('Интерфейс TUN',vl.interface||'maxvpn0')+" in html
    assert "row('Интерфейс TUN',v.interface||'maxvpn0')+" not in html


def test_vless_selection_ui_distinguishes_live_state_from_pending_choice():
    html = SOURCE_HTML.read_text(encoding="utf-8")
    assert "ФАКТИЧЕСКИЙ ТЕКУЩИЙ СЕРВЕР" in html
    renderer_start = html.index("function renderVless(){")
    renderer_end = html.index("function renderVlessProfiles(){", renderer_start)
    renderer = html[renderer_start:renderer_end]
    assert (
        "const desiredMode=v.desired_selection_mode||v.selection_mode||'unknown';"
        in renderer
    )
    assert "const selectionPending=v.selection_pending===true;" in renderer
    assert "Ожидает применения:" in renderer
    assert "фактический выбор sing-box не меняется" in renderer
    assert "Автовыбор ожидает применения" in renderer
    assert "Автовыбор не подтверждён" in renderer
    assert "Выбрать автовыбор" in renderer


def test_vless_profile_row_marks_desired_manual_profile_as_pending_until_apply():
    html = SOURCE_HTML.read_text(encoding="utf-8")
    start = html.index("function renderVlessProfiles(){")
    end = html.index("function renderVlessSelectionHistory(){", start)
    renderer = html[start:end]
    assert "Будет выбран после применения" in renderer
    assert "Сейчас используется" in renderer
    assert "Выбрано к применению" in renderer
    assert "Выбрать к применению" in renderer
    assert "isActive=active===`vless-profile-${p.id}`" in renderer


def test_vless_apply_ui_reports_success_only_after_runtime_confirmation():
    html = SOURCE_HTML.read_text(encoding="utf-8")
    start = html.index("async function applyVless(){")
    end = html.index("async function stopVless(){", start)
    apply_handler = html[start:end]
    assert "state.vless?.selection_pending" in apply_handler
    assert "фактический режим/профиль sing-box не совпал" in apply_handler
    assert "Изменения применены и подтверждены работающим sing-box" in apply_handler


def test_vless_history_and_profile_list_are_collapsed_by_default():
    html = SOURCE_HTML.read_text(encoding="utf-8")
    assert "vlessHistoryExpanded:false" in html
    assert "vlessProfilesExpanded:false" in html
    assert 'id="vlessProfilesDisclosure" style="display:none"' in html
    assert "function toggleVlessSelectionHistory()" in html
    assert "Показать историю" in html
    assert "Скрыть историю" in html


def test_vless_current_server_shows_country_and_only_actual_runtime_endpoint():
    html = SOURCE_HTML.read_text(encoding="utf-8")
    start = html.index("function renderVless(){")
    end = html.index("function renderVlessProfiles(){", start)
    renderer = html[start:end]
    assert (
        "const activeRuntimeConfirmed=v.running===true&&Boolean(active||v.active_server_address);"
        in renderer
    )
    assert (
        "const activeCountry=activeRuntimeConfirmed?vlessCountry(activeCountryProfile):null;"
        in renderer
    )
    assert (
        "vlessCountryFlagHtml(activeCountryProfile)" in renderer
        or "vlessCountryFlagHtml(active)" in renderer
    )
    assert "active?`${active.address}:${active.port}`" in renderer
    assert "sing-box остановлен" in renderer
    assert "Режим не подтверждён" in renderer


# MAXVPN-APPLIANCE-URLTEST-MEASUREMENTS-V1


def test_vless_urltest_measurements_panel_uses_existing_sing_box_snapshot():
    html = SOURCE_HTML.read_text(encoding="utf-8")
    assert 'id="vlessUrltestMeasurementsPanel"' in html

    start = html.index("function renderVlessUrltestMeasurements(){")
    end = html.index("async function refreshVlessSelectionHistory(){", start)
    renderer = html[start:end]

    assert "const journal=state.vlessSelectionHistory||{};" in renderer
    assert "const current=journal.current||null;" in renderer
    assert "(state.vless?.profiles||[]).filter(profile=>profile.enabled)" in renderer
    assert "vlessUrltestSampleState(profile)" in renderer
    assert "vlessProfileMeasurement(profile)" in renderer
    assert "vless-urltest-card-active" in renderer
    assert "state.vless?.running===true" in renderer
    assert "renderVlessUrltestMeasurements();" in html
    assert "перечитывает результаты API sing-box и истории ручных проверок" in renderer
    assert "новую проверку не запускает" in renderer
    assert "маршрут и выбранный сервер не меняет" in renderer


def test_vless_urltest_panel_distinguishes_active_runtime_and_manual_delays():
    html = SOURCE_HTML.read_text(encoding="utf-8")
    start = html.index("function renderVlessUrltestMeasurements(){")
    end = html.index("async function refreshVlessSelectionHistory(){", start)
    renderer = html[start:end]
    assert "state.vless?.running===true" in renderer
    assert "state.vless?.active_outbound||current?.active_outbound||null" in renderer
    assert "sampleIsManual" in renderer
    helper_start = html.index("function vlessUrltestSampleState(profile){")
    helper_end = html.index("function vlessProfileMeasurement(", helper_start)
    sample_helper = html[helper_start:helper_end]
    assert "sample.delay_ms===manualSample.delay_ms" in sample_helper
    assert "Math.abs(sampleEpoch-manualEpoch)<=12000" in sample_helper
    assert "URLTest" in renderer
    assert "не пропускная способность" in renderer
    assert "api('/api/appliance/v1/vless/delays'" not in renderer


def test_vless_urltest_measurement_panel_is_visible_before_server_list():
    html = SOURCE_HTML.read_text(encoding="utf-8")
    assert html.index('id="vlessUrltestMeasurementsPanel"') < html.index(
        "<h2>Список серверов</h2>"
    )


# MAXVPN-APPLIANCE-HISTORY-UX-V2


def test_vless_active_auto_mode_does_not_repeat_status_in_disabled_button():
    html = SOURCE_HTML.read_text(encoding="utf-8")
    renderer = html[
        html.index("function renderVless(){") : html.index(
            "function renderVlessProfiles(){"
        )
    ]
    assert "v.selection_mode==='auto'?'Автовыбор активен'" in renderer
    assert (
        "autoButton.style.display=desiredMode==='auto'&&!selectionPending&&v.selection_mode==='auto'?'none':''"
        in renderer
    )


def test_selection_history_uses_live_runtime_for_actual_current_server():
    html = SOURCE_HTML.read_text(encoding="utf-8")
    start = html.index("function renderVlessSelectionHistory(){")
    end = html.index("function toggleVlessSelectionHistory(){", start)
    renderer = html[start:end]
    assert "const runtime=state.vless||{}" in renderer
    assert "const liveTag=running?(runtime.active_outbound||null):null" in renderer
    assert "Фактическое состояние runtime" in renderer
    assert "Снимок истории не совпадает с runtime" in renderer
    assert "Задержка из старого снимка не приписывается текущему серверу" in renderer


def test_selection_history_details_are_collapsed_and_event_types_are_distinguished():
    html = SOURCE_HTML.read_text(encoding="utf-8")
    start = html.index("function renderVlessSelectionHistory(){")
    end = html.index("function toggleVlessSelectionHistory(){", start)
    renderer = html[start:end]
    assert '<details class="vless-history-detail">' in renderer
    assert "Ручной выбор / смена режима" in renderer
    assert "История выбора сервера" in renderer
    assert (
        "Точная причина переключения показывается только когда хватает актуальных измерений"
        in renderer
    )


# MAXVPN-COUNTRY-FLAG-SVG-V3


def test_vless_country_svg_flags_cover_all_provider_countries_and_aliases():
    html = SOURCE_HTML.read_text(encoding="utf-8")
    expected = {
        "us": "США",
        "tr": "Турция",
        "ru": "Россия",
        "uk": "Великобритания",
        "gb": "Великобритания",
        "kz": "Казахстан",
        "se": "Швеция",
        "fr": "Франция",
        "at": "Австрия",
        "de": "Германия",
        "it": "Италия",
        "nl": "Нидерланды",
        "fi": "Финляндия",
        "pl": "Польша",
        "lv": "Латвия",
        "lt": "Литва",
        "ch": "Швейцария",
        "ae": "ОАЭ",
        "jp": "Япония",
        "hk": "Гонконг",
        "ca": "Канада",
    }
    for code, name in expected.items():
        assert f"{code}:{{name:'{name}'" in html
    matcher = re.search(r"host\.match\(/\^\(([^)]*)\)", html)
    assert matcher
    assert set(expected).issubset(set(matcher.group(1).split("|")))
    start = html.index("const VLESS_COUNTRY_FLAG_SVGS=Object.freeze({")
    end = html.index("function vlessCountryFlagHtml(profile){", start)
    artwork = html[start:end]
    for code in (
        "us:",
        "tr:",
        "ru:",
        "uk:",
        "gb:",
        "kz:",
        "se:",
        "fr:",
        "at:",
        "de:",
        "it:",
        "nl:",
        "fi:",
        "pl:",
        "lv:",
        "lt:",
        "ch:",
        "ae:",
        "jp:",
        "hk:",
        "ca:",
    ):
        assert code in artwork
    assert "https://" not in artwork
    assert "data:image" not in artwork
    assert "vlessCountryFlagHtml(p)" in html
    assert "MAXVPN-COUNTRY-FLAG-SVG-V3" in html


# MAXVPN-APPLIANCE-HISTORY-PAGINATION-V1


def test_selection_history_shows_five_then_expands_by_five():
    html = SOURCE_HTML.read_text(encoding="utf-8")
    renderer = html[
        html.index("function renderVlessSelectionHistory(){") : html.index(
            "function toggleVlessSelectionHistory(){"
        )
    ]
    assert "vlessHistoryVisibleCount:5" in html
    assert "journal.events.slice().reverse()" in renderer
    assert "allEvents.slice(0,visibleCount)" in renderer
    assert "Показать историю (${allEvents.length})" in renderer
    assert "Показано ${events.length} из ${allEvents.length} событий" in renderer
    assert "Показать ещё ${Math.min(5,allEvents.length-events.length)}" in renderer
    assert "function showMoreVlessSelectionHistory()" in html


def test_active_server_latency_requires_matching_runtime_snapshot():
    html = SOURCE_HTML.read_text(encoding="utf-8")
    renderer = html[
        html.index("function renderVless(){") : html.index(
            "function renderVlessProfiles(){"
        )
    ]
    assert 'id="vlessActiveMeasurement"' in html
    measurement_renderer = html[
        html.index("function renderVlessActiveMeasurement(){") : html.index(
            "function renderVless(){"
        )
    ]
    assert "String(current.active_outbound||'')!==liveTag" in measurement_renderer
    assert "vlessCurrentUrltestMeasurement(current)" in measurement_renderer
    assert "renderVlessActiveMeasurement();" in renderer
    assert "vlessCurrentUrltestMeasurement(current)" in measurement_renderer
    assert "снимок не совпадает с активным сервером" in measurement_renderer


def test_active_server_measurement_has_separate_spaced_line():
    html = SOURCE_HTML.read_text(encoding="utf-8")
    assert (
        '<small id="vlessActiveMeasurement" '
        'style="display:block;margin-top:6px;line-height:1.45">'
    ) in html


def test_overview_current_server_latency_uses_ping_label_and_matches_active_snapshot():
    html = SOURCE_HTML.read_text(encoding="utf-8")
    assert "latencyNode.id='ovMetric3Latency'" in html
    assert "const current=state.vlessSelectionHistory?.current||null;" in html
    assert "runtimeTag===measurementTag&&delay!==null?`Пинг ${delay}`:'—'" in html
    assert "Math.round(Number(rawDelay))" in html
    assert "$('ovMetric3Help').insertAdjacentElement('afterend',latencyNode)" in html


def test_vless_urltest_snapshot_displays_active_profile_endpoint():
    html = SOURCE_HTML.read_text(encoding="utf-8")
    start = html.index("function renderVlessUrltestMeasurements(){")
    end = html.index("async function refreshVlessSelectionHistory(){", start)
    renderer = html[start:end]

    assert (
        "const activeProfile=active?(state.vless?.profiles||[]).find(profile=>active===`vless-profile-${profile.id}`):null;"
        in renderer
    )
    assert (
        "const activeLabel=activeProfile?`${activeProfile.address}:${activeProfile.port}`:(active||'не определён');"
        in renderer
    )
    assert "активный узел: ${activeLabel}" in renderer
    assert "активный узел: ${active||'не определён'}" not in renderer


def test_vless_active_measurement_refreshes_with_selection_snapshot():
    html = SOURCE_HTML.read_text(encoding="utf-8")

    helper_start = html.index("function renderVlessActiveMeasurement(){")
    helper_end = html.index("function renderVless(){", helper_start)
    helper = html[helper_start:helper_end]

    assert "state.vlessSelectionHistory?.current||null" in helper
    assert "vlessCurrentUrltestMeasurement(current)" in helper
    assert "current.active_outbound||'')!==liveTag" in helper

    refresh_start = html.index("async function refreshVlessSelectionHistory(){")
    refresh_end = html.index("async function refreshVless(){", refresh_start)
    refresh = html[refresh_start:refresh_end]

    assert "renderVlessActiveMeasurement();" in refresh
    assert refresh.index("renderVlessActiveMeasurement();") < refresh.index(
        "renderVlessSelectionHistory();"
    )

    renderer_start = html.index("function renderVless(){")
    renderer_end = html.index("function renderVlessProfiles(){", renderer_start)
    assert "renderVlessActiveMeasurement();" in html[renderer_start:renderer_end]


# MAXVPN-BRUME-OUTAGE-FALLBACK-V1


def test_brume_outage_history_is_used_when_urltest_has_no_numeric_delay():
    html = SOURCE_HTML.read_text(encoding="utf-8")
    start = html.index("function vlessProfileMeasurement(profile){")
    end = html.index("function renderVlessActiveMeasurement(){", start)
    helper = html[start:end]

    # Manual outage is a distinct observation for profiles without successful URLTest history.
    assert "availability?.reason==='no_successful_history'" in helper
    assert "manualSample?.reachable===false" in helper
    assert "manualSample?.first_failed_at" in helper
    assert "const failedAt=manualSample.first_failed_at;" in helper
    assert "manual-outage" in helper
    assert "consecutive_failures" in helper
    assert "formatVlessDuration(seconds)" in helper

    # A newer successful URLTest result must supersede an older manual failure.
    assert "hasNewerSuccessfulUrltest" in helper
    assert "sampleEpoch>failedEpoch" in helper
    assert "if(!hasNewerSuccessfulUrltest)" in helper
    assert "typeof sample?.delay_ms==='number'" in helper

    # The manual outage branch must precede the generic URLTest fallback.
    outage_index = helper.index("if(!hasNewerSuccessfulUrltest)")
    outage_return = helper.index("source:'manual-outage'", outage_index)
    urltest_return = helper.index("return {source:'urltest',delay_ms:delay")
    assert outage_index < outage_return < urltest_return

    # Preserve separate handling of manual measurements and stale results.
    assert "manualSample?.last_checked_at" in helper
    assert "vlessDelay(profile.id)" in helper
    assert "vlessDelayDetails(profile.id)" in helper
    assert "source:'manual-stale'" in helper
    assert "source:'urltest-monitor'" in helper
