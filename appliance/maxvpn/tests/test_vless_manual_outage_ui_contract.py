from pathlib import Path

HTML = Path(__file__).resolve().parents[1] / "index.html"


def test_manual_failure_downtime_is_rendered_for_profiles_without_urltest_history():
    source = HTML.read_text(encoding="utf-8")
    function_start = source.index("function vlessProfileMeasurement(profile){")
    function_end = source.index("\nfunction ", function_start + 1)
    function = source[function_start:function_end]
    assert "availability?.reason==='no_successful_history'" in function
    assert "manualSample?.first_failed_at" in function
    assert "manualSample?.reachable===false" in function
    assert "Нет ответа по ручной проверке" in function
    assert "consecutive_failures" in function
    assert function.index("manual-outage") < function.index(
        "if((!sample||sampleIsManual)"
    )
    assert "measurement.source==='manual-outage'" in source
