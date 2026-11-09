from pathlib import Path


def test_urltest_cards_keep_fresh_manual_ping_visible_and_labeled():
    path = Path(__file__).parents[1] / "index.html"
    source = path.read_text(encoding="utf-8")
    start = source.index("function renderVlessUrltestMeasurements(){")
    end = source.find("\nasync function refreshVlessSelectionHistory", start)
    if end < 0:
        end = source.find("\nfunction refreshVlessSelectionHistory", start)
    assert end > start
    renderer = source[start:end]

    assert "const measurement=vlessProfileMeasurement(profile)||{};" in renderer
    assert "const isManual=source==='manual';" in renderer
    assert "Ручная проверка · измерено" in renderer
    assert "const delay=typeof measurement.delay_ms==='number'" in renderer
    assert 'title="${vlessEscape(ageTitle)}"' in renderer
    assert (
        "Недавний результат ручной проверки исключён из URLTest; ожидается следующий автоматический замер"
        not in renderer
    )
    assert (
        "Если свежего URLTest нет, отображается последняя ручная проверка BRUME 3 с явной маркировкой"
        in source
    )
