from dataclasses import dataclass

from backend.models.server_metrics import ServerMetrics


@dataclass(slots=True)
class Server:
    id: int
    name: str
    country: str
    city: str
    endpoint: str
    public_key: str

    online: bool = True
    maintenance: bool = False

    load: int = 0
    latency: int = 0

    max_load: int = 80
    max_devices: int = 1000

    metrics: ServerMetrics | None = None
