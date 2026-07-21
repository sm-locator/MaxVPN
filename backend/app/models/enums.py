from enum import Enum


class VPNProtocol(str, Enum):
    WIREGUARD = "wireguard"
    AMNEZIAWG = "amneziawg"
    OPENVPN = "openvpn"
    XRAY = "xray"


class ServerStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    MAINTENANCE = "maintenance"
