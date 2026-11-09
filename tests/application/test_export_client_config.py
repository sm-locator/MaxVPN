from pathlib import Path

from backend.application.use_cases.export_client_config import (
    ExportClientConfigUseCase,
)
from backend.services.wireguard_config_renderer import (
    WireGuardConfigRenderer,
)
from tests.factories import make_client_config


def test_export_client_config(tmp_path: Path):
    use_case = ExportClientConfigUseCase(
        WireGuardConfigRenderer(),
    )

    destination = tmp_path / "client.conf"

    path = use_case.execute(
        make_client_config(),
        destination,
    )

    assert path.exists()

    text = path.read_text()

    assert "[Interface]" in text
    assert "[Peer]" in text
