"""Bot commands (§4.2.2). Filled in by T17 (/web) and T18 (the rest)."""

from aiogram import Router


def register(router: Router) -> None:
    """Attach the command handlers to the router (before the catch-all message handler)."""
