from app.exporters.qr_exporter import QRExporter


def test_export_returns_png_bytes() -> None:
    exporter = QRExporter()

    png = exporter.export("Hello")

    assert isinstance(png, bytes)
    assert png.startswith(b"\x89PNG")
    assert len(png) > 100
