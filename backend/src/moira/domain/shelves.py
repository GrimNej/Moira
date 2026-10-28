"""The 10 fixed shelves (§1.6) and their ring positions (§7.7.1)."""

import math

SHELVES: tuple[str, ...] = (
    "People",
    "Links & reads",
    "Music",
    "Watch list",
    "Places",
    "Ideas",
    "To-dos",
    "Tech & setup",
    "Learning",
    "Misc",
)
RING_RADIUS = 1100.0


def shelf_position(index: int) -> tuple[float, float]:
    """Evenly spaced on the ring, clockwise from 12 o'clock (screen y grows downward)."""
    angle = 2 * math.pi * index / len(SHELVES)
    return RING_RADIUS * math.sin(angle), -RING_RADIUS * math.cos(angle)
