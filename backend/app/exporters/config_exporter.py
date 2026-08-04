from fastapi.responses import PlainTextResponse


class ConfigExporter:
    def export(
        self,
        config: str,
        filename: str,
    ) -> PlainTextResponse:
        return PlainTextResponse(
            content=config,
            headers={
                "Content-Disposition": (f'attachment; filename="{filename}.conf"'),
            },
        )
