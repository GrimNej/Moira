"""Job handlers, registered by kind (§7.0). Each pipeline task adds its handlers here."""

from moira.jobs.worker import Handler

PRE_FILE_KINDS = ("read_link", "transcribe", "read_video", "read_pdf")


def registry() -> dict[str, Handler]:
    """The handler map. Filled by ``moira.app_services.build_handlers`` at startup."""
    return {}
