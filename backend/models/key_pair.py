from dataclasses import dataclass


@dataclass(slots=True)
class KeyPair:
    private_key: str
    public_key: str
