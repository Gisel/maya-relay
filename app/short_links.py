import secrets

_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def generate_short_token(length: int = 8) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))
