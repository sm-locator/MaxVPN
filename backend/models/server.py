from dataclasses import dataclass


@dataclass(slots=True)
class Server:
    id: int
    name: str
    country: str
    city: str

    online: bool = True

    load: int = 0

    max_devices: int = 1000
