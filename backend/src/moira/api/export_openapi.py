"""Write the OpenAPI document (``make openapi`` writes docs/reference/openapi.json)."""

import json
import sys
from pathlib import Path

from moira.config import Settings
from moira.main import create_app


def main() -> None:
    # Placeholder settings: the schema does not depend on secrets or the environment.
    settings = Settings(
        app_env="test",
        public_base_url="https://moira.example",
        telegram_bot_token="0:openapi",  # noqa: S106
        telegram_bot_username="moira_bot",
        owner_telegram_id=0,
    )
    schema = create_app(settings).openapi()
    schema["info"]["version"] = "see /api/health"
    text = json.dumps(schema, indent=2, sort_keys=True) + "\n"
    # Write the file directly so Windows shells cannot turn the newlines into CRLF.
    Path(sys.argv[1]).write_text(text, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
