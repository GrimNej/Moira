"""Owner CLI (App. A): python -m moira.admin invite --role judge --uses 50 --until 2026-11-20."""

import argparse
import sys
from datetime import date

from moira.accounts import create_invite
from moira.app_services import startup_services
from moira.config import load_settings


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="moira.admin")
    sub = parser.add_subparsers(dest="cmd", required=True)
    inv = sub.add_parser("invite", help="create an invite code (printed once)")
    inv.add_argument("--role", choices=["tester", "judge"], required=True)
    inv.add_argument("--uses", type=int, default=1)
    inv.add_argument("--until", type=date.fromisoformat, required=True)
    args = parser.parse_args(argv)
    settings = load_settings()
    services = startup_services(settings)
    if args.cmd == "invite":
        code = create_invite(services, args.role, args.uses, args.until)
        sys.stdout.write(
            f"{args.role} invite, {args.uses} uses, until {args.until}:\n"
            f"https://t.me/{settings.telegram_bot_username}?start={code}\n"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
