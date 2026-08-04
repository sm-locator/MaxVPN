import io

import qrcode


class QRExporter:
    def export(
        self,
        config: str,
    ) -> bytes:
        qr = qrcode.make(config)

        buffer = io.BytesIO()
        qr.save(buffer, format="PNG")

        return buffer.getvalue()
