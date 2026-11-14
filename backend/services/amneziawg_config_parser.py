from __future__ import annotations

from backend.models.amneziawg_config import (
    AmneziaWGConfig,
    AmneziaWGInterface,
    AmneziaWGPeer,
)


class AmneziaWGConfigError(ValueError):
    """Raised when an AmneziaWG configuration is invalid."""


class AmneziaWGConfigParser:
    """Parses a provider AmneziaWG configuration."""

    _INTERFACE_KEYS = {
        "PrivateKey",
        "Address",
        "DNS",
        "MTU",
        "Jc",
        "Jmin",
        "Jmax",
        "S1",
        "S2",
        "S3",
        "S4",
        "H1",
        "H2",
        "H3",
        "H4",
        "I1",
        "I2",
        "I3",
        "I4",
        "I5",
    }

    _PEER_KEYS = {
        "PublicKey",
        "PresharedKey",
        "AllowedIPs",
        "PersistentKeepalive",
        "Endpoint",
    }

    def parse(self, text: str) -> AmneziaWGConfig:
        section: str | None = None
        values: dict[str, dict[str, list[str]]] = {
            "Interface": {},
            "Peer": {},
        }

        for line_number, raw_line in enumerate(text.splitlines(), start=1):
            line = raw_line.strip()

            if not line or line.startswith("#"):
                continue

            if line.startswith("[") and line.endswith("]"):
                section = line[1:-1].strip()

                if section not in values:
                    raise AmneziaWGConfigError(
                        f"Unsupported section [{section}] at line {line_number}"
                    )

                continue

            if section is None:
                raise AmneziaWGConfigError(
                    f"Key/value outside a section at line {line_number}"
                )

            if "=" not in line:
                raise AmneziaWGConfigError(
                    f"Invalid key/value at line {line_number}: {raw_line!r}"
                )

            key, raw_value = line.split("=", 1)
            key = key.strip()
            value = raw_value.strip()

            allowed_keys = (
                self._INTERFACE_KEYS if section == "Interface" else self._PEER_KEYS
            )

            if key not in allowed_keys:
                raise AmneziaWGConfigError(
                    f"Unsupported key {key!r} in [{section}] at line {line_number}"
                )

            if key in values[section] and key != "AllowedIPs":
                raise AmneziaWGConfigError(
                    f"Duplicate key {key!r} in [{section}] at line {line_number}"
                )

            values[section].setdefault(key, []).append(value)

        interface = self._parse_interface(values["Interface"])
        peer = self._parse_peer(values["Peer"])

        return AmneziaWGConfig(
            interface=interface,
            peer=peer,
        )

    @staticmethod
    def _single(
        section: dict[str, list[str]],
        key: str,
        *,
        required: bool = False,
    ) -> str | None:
        items = section.get(key)

        if not items:
            if required:
                raise AmneziaWGConfigError(f"Missing required key: {key}")
            return None

        if len(items) != 1:
            raise AmneziaWGConfigError(f"Duplicate key: {key}")

        value = items[0]

        if required and not value:
            raise AmneziaWGConfigError(f"Missing required key: {key}")

        return value

    def _parse_interface(
        self,
        section: dict[str, list[str]],
    ) -> AmneziaWGInterface:
        private_key = self._single(section, "PrivateKey", required=True)
        address = self._single(section, "Address", required=True)

        mtu = self._parse_int(section, "MTU")
        jc = self._parse_int(section, "Jc")
        jmin = self._parse_int(section, "Jmin")
        jmax = self._parse_int(section, "Jmax")
        s1 = self._parse_int(section, "S1")
        s2 = self._parse_int(section, "S2")
        s3 = self._parse_int(section, "S3")
        s4 = self._parse_int(section, "S4")

        return AmneziaWGInterface(
            private_key=private_key,
            address=address,
            mtu=mtu,
            dns=self._single(section, "DNS"),
            jc=jc,
            jmin=jmin,
            jmax=jmax,
            s1=s1,
            s2=s2,
            s3=s3,
            s4=s4,
            h1=self._single(section, "H1"),
            h2=self._single(section, "H2"),
            h3=self._single(section, "H3"),
            h4=self._single(section, "H4"),
            i1=self._single(section, "I1"),
            i2=self._single(section, "I2"),
            i3=self._single(section, "I3"),
            i4=self._single(section, "I4"),
            i5=self._single(section, "I5"),
        )

    def _parse_peer(
        self,
        section: dict[str, list[str]],
    ) -> AmneziaWGPeer:
        public_key = self._single(section, "PublicKey", required=True)
        endpoint = self._single(section, "Endpoint", required=True)

        allowed_ips = tuple(
            item.strip()
            for raw_value in section.get("AllowedIPs", ())
            for item in raw_value.split(",")
            if item.strip()
        )

        if not allowed_ips:
            raise AmneziaWGConfigError("Missing required key: AllowedIPs")

        persistent_keepalive = self._parse_int(
            section,
            "PersistentKeepalive",
        )

        return AmneziaWGPeer(
            public_key=public_key,
            allowed_ips=allowed_ips,
            endpoint=endpoint,
            persistent_keepalive=persistent_keepalive,
            preshared_key=self._single(section, "PresharedKey"),
        )

    @classmethod
    def _parse_int(
        cls,
        section: dict[str, list[str]],
        key: str,
    ) -> int | None:
        value = cls._single(section, key)

        if value is None:
            return None

        try:
            return int(value)
        except ValueError as exc:
            raise AmneziaWGConfigError(
                f"{key} must be an integer, got {value!r}"
            ) from exc
