from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined


class TemplateRenderer:
    """Renders VPN configuration templates."""

    def __init__(self) -> None:
        templates_path = Path(__file__).parent / "templates"

        self._environment = Environment(
            loader=FileSystemLoader(templates_path),
            undefined=StrictUndefined,
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def render(
        self,
        template_name: str,
        context: dict[str, Any],
    ) -> str:
        template = self._environment.get_template(template_name)
        return template.render(**context)
