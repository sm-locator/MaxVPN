from __future__ import annotations

from dataclasses import dataclass

from backend.models.amneziawg_config import AmneziaWGConfig
from backend.services.amneziawg_config_parser import (
    AmneziaWGConfigParser,
)
from backend.services.amneziawg_config_renderer import (
    AmneziaWGConfigRenderer,
)


@dataclass(frozen=True, slots=True)
class AmneziaWGRuntimeConfig:
    """AWG configuration suitable for awg setconf/syncconf."""

    text: str


class AmneziaWGRuntimeConfigGenerator:
    """
    Parses a provider AmneziaWG profile and produces the runtime
    configuration consumed by awg setconf/syncconf.
    """

    def __init__(
        self,
        parser: AmneziaWGConfigParser | None = None,
        renderer: AmneziaWGConfigRenderer | None = None,
    ) -> None:
        self._parser = parser or AmneziaWGConfigParser()
        self._renderer = renderer or AmneziaWGConfigRenderer()

    def generate(self, provider_config: str) -> AmneziaWGRuntimeConfig:
        config: AmneziaWGConfig = self._parser.parse(provider_config)

        runtime_text = self._renderer.render_awg_runtime(config)

        return AmneziaWGRuntimeConfig(text=runtime_text)
