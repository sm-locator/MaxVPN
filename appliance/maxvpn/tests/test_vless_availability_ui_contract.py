from pathlib import Path

HTML = Path(__file__).resolve().parents[1] / "index.html"


def test_lan_vless_measurement_uses_persistent_urltest_availability():
    html = HTML.read_text(encoding="utf-8")
    assert "profile_availability" in html
    assert "availability?.status==='no_result'" in html
    assert "Нет успешного измерения" in html
    assert "Старая ручная проверка" in html
    assert "if(age!==null&&limit!==null&&age<=limit)" in html
    assert "source:'manual-stale',delay_ms:null" in html
    assert (
        "successful_history_disappeared" not in html
    )  # backend reason is not a UI hard-code
    assert "не подтверждает текущее состояние сервера" in html
    assert "История sing-box могла быть сброшена или перезапущена" in html


def test_lan_vless_availability_refresh_repaints_profile_rows():
    html = HTML.read_text(encoding="utf-8")
    assert "if(state.vless)renderVlessProfiles();" in html


def test_kill_switch_ui_maps_fallback_policy_and_explains_direct_wan_exposure():
    html = HTML.read_text(encoding="utf-8")
    assert 'id="vlessKillSwitchButton" type="button"' in html
    assert 'onclick="toggleVlessKillSwitch()"' in html
    assert "const killSwitchOn=settings.wan_fallback_enabled!==true;" in html
    assert (
        "killSwitchButton.textContent='Kill Switch: '+(killSwitchOn?'ON':'OFF');"
        in html
    )
    assert "ON — LAN остаётся заблокированным при отказе VPN." in html
    assert "OFF — при отказе VPN разрешён переход LAN напрямую через WAN." in html
    assert (
        "после двух последовательных неудачных проверок LAN временно переключится напрямую на WAN"
        in html
    )
    assert "вне VLESS и AmneziaWG" in html
    assert "JSON.stringify({wan_fallback_enabled:nextFallbackEnabled})" in html
    assert "v.wan_fallback_active===true" in html
    assert 'id="vlessWanFallback" type="checkbox"' not in html
