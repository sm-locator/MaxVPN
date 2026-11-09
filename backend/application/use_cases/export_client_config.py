from __future__ import annotations

from pathlib import Path

from backend.models.client_config import ClientConfig
from backend.ports.config_renderer import ConfigRenderer


class ExportClientConfigUseCase:
    """
    Exports a client configuration to a file.
    """

    def __init__(
        self,
        renderer: ConfigRenderer,
    ):
        self._renderer = renderer

    def execute(
        self,
        config: ClientConfig,
        destination: Path,
    ) -> Path:
        text = self._renderer.render(config)

        destination.write_text(
            text,
            encoding="utf-8",
        )

        return destination
