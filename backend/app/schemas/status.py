from pydantic import BaseModel, ConfigDict


class ComponentStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    reason: str | None = None


class MaxVPNStatusRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    router: ComponentStatus
    vpn: ComponentStatus
    smart_routing: ComponentStatus
