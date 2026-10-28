"""Public identifiers: a prefix plus 12 random URL-safe characters (blueprint §6)."""

import secrets

PREFIXES = frozenset({"n_", "h_", "p_", "u_", "s_", "c_", "t_"})


def new(prefix: str) -> str:
    """Return a new public id such as ``n_Xb3k9Q-aZ0pL``.

    9 random bytes encode to exactly 12 URL-safe base64 characters.
    """
    if prefix not in PREFIXES:
        raise ValueError(f"unknown id prefix: {prefix!r}")
    return prefix + secrets.token_urlsafe(9)
