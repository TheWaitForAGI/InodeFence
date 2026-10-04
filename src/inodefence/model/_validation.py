"""Shared scalar validation for public immutable evidence constructors."""


def validate_sha256(value: object) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError("digest must be a lowercase SHA-256 hex string")
