"""Registers the pipeline handler factories (read_link, research, media, nightly, …).

Each task adds its factory here; ``jobs.handlers.build`` merges them.
"""

from moira.services import Services


def register(services: Services) -> None:
    factories = services.extras.setdefault("handler_factories", [])
    factories.clear()
