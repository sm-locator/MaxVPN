from fastapi import Response

from app.exporters.config_exporter import ConfigExporter
from app.exporters.qr_exporter import QRExporter


class ExportFacade:
    def __init__(
        self,
        config_exporter: ConfigExporter,
        qr_exporter: QRExporter,
    ) -> None:
        self._config_exporter = config_exporter
        self._qr_exporter = qr_exporter

    def export_config(
        self,
        config: str,
        filename: str,
    ) -> Response:
        return self._config_exporter.export(
            config=config,
            filename=filename,
        )

    def export_qr(
        self,
        config: str,
    ) -> bytes:
        return self._qr_exporter.export(config)
