from __future__ import annotations


def validate_domain_target(target: str) -> str:
    value = target.strip().lower().rstrip(".")

    if value.startswith("*."):
        value = value[2:]

    if not value:
        raise ValueError("domain must not be empty")

    if any(character in value for character in "/?#@:"):
        raise ValueError(
            "domain must contain only a hostname without scheme, path or parameters"
        )

    if "://" in value or "@" in value:
        raise ValueError(
            "domain must contain only a hostname without scheme, path or parameters"
        )

    if len(value) > 253:
        raise ValueError("domain is too long")

    labels = value.split(".")

    if len(labels) < 2:
        raise ValueError("domain must contain at least two labels")

    if any(not label for label in labels):
        raise ValueError("domain contains an empty label")

    for label in labels:
        if len(label) > 63:
            raise ValueError("domain label is too long")

        if label[0] == "-" or label[-1] == "-":
            raise ValueError("domain labels must not start or end with '-'")

        if not all(character.isalnum() or character == "-" for character in label):
            raise ValueError("domain contains invalid characters")

    return value
