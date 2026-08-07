from dataclasses import dataclass


@dataclass(slots=True)
class Device:
    id: int
    name: str
    fingerprint: str
    active: bool = True
    trusted: bool = False
