from pathlib import Path

HTML = Path(__file__).resolve().parents[1] / "index.html"


def test_newer_urltest_success_overrides_persisted_no_result_status():
    source = HTML.read_text(encoding="utf-8")
    fn = source[source.index("function vlessProfileMeasurement(profile){") :]
    fn = fn[: fn.index("\nfunction ")]
    assert "urltestObservedAt>missingObservedAt" in fn
    assert "source:'urltest'" in source
    assert "return urltestObservation" in fn
    assert fn.index("return urltestObservation") < fn.index(
        "if(availability?.status==='no_result'"
    )


def test_manual_failure_expires_after_configured_freshness_interval():
    source = HTML.read_text(encoding="utf-8")
    assert "const stale=age===null||limit===null||age>limit;" in source
    assert "source:'manual-outage-stale'" in source
    assert "текущая доступность неизвестна" in source
    assert "Результат ручной проверки устарел" in source


def test_server_badges_and_filters_use_effective_measurement_source():
    source = HTML.read_text(encoding="utf-8")
    assert "typeof measurement.delay_ms==='number'" in source
    assert "measurement.source==='manual-outage'" in source
    assert "staleMeasurement?" in source
    assert "filter==='reachable'&&typeof measurement.delay_ms!=='number'" in source
    assert "filter==='failed'&&measurement.source!=='manual-outage'" in source
    assert "filter==='stale'" in source
    assert '<option value="stale">Проверка устарела</option>' in source


def test_urltest_grid_also_labels_stale_manual_failure():
    source = HTML.read_text(encoding="utf-8")
    assert "rowMeasurement?.source==='manual-outage-stale'" not in source
    assert "'manual-outage-stale','manual-stale'" in source
