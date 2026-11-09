from enum import StrEnum

from backend.services.smart_routing_target_validation import validate_domain_target
from pydantic import BaseModel, ConfigDict, Field, model_validator


class SmartRoutingTargetType(StrEnum):
    CIDR = "cidr"
    DOMAIN = "domain"


class SmartRoutingAction(StrEnum):
    DIRECT = "direct"
    VPN = "vpn"


class SmartRoutingAddressFamily(StrEnum):
    ANY = "any"
    IPV4 = "ipv4"
    IPV6 = "ipv6"


class SmartRoutingRuleCreate(BaseModel):
    target_type: SmartRoutingTargetType
    target: str = Field(min_length=1, max_length=255)
    action: SmartRoutingAction
    priority: int = Field(ge=0)
    address_family: SmartRoutingAddressFamily = SmartRoutingAddressFamily.ANY
    enabled: bool = True

    @model_validator(mode="after")
    def validate_domain_target(self):
        if self.target_type is SmartRoutingTargetType.DOMAIN:
            validate_domain_target(self.target)
        return self


class SmartRoutingRuleUpdate(BaseModel):
    target_type: SmartRoutingTargetType | None = None
    target: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
    )
    action: SmartRoutingAction | None = None
    priority: int | None = Field(
        default=None,
        ge=0,
    )
    address_family: SmartRoutingAddressFamily | None = None
    enabled: bool | None = None

    @model_validator(mode="after")
    def validate_domain_target(self):
        if (
            self.target_type is SmartRoutingTargetType.DOMAIN
            and self.target is not None
        ):
            validate_domain_target(self.target)
        elif self.target is not None and any(
            marker in self.target.lower() for marker in ("http://", "https://")
        ):
            raise ValueError("target must contain only a hostname or IP address/CIDR")
        return self


class SmartRoutingRuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    target_type: SmartRoutingTargetType
    target: str
    action: SmartRoutingAction
    priority: int
    address_family: SmartRoutingAddressFamily
    enabled: bool
