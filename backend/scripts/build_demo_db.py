"""Build templates/demo.db from data/demo/nuggets.jsonl (§11.3, ``make demo-template``).

Uses the contributor model when MODEL_API_KEY is set (synthetic data only), else FakeLLM.
Also writes web/public/welcome-sky.json, the static sky drawn on the signed-out Welcome screen.
"""

import argparse
import asyncio
import sys
from pathlib import Path

from moira.clock import SystemClock
from moira.config import load_settings
from moira.demo import ROOT, build_template
from moira.embed.model import load_embedder


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--fake", action="store_true", help="use FakeLLM even with an API key")
    args = ap.parse_args(argv)
    settings = load_settings()
    embedder = load_embedder(
        settings.embed_model,
        settings.embed_dim,
        settings.embed_quantize,
        fake=settings.app_env == "test",
    )
    llm = None
    if args.fake or settings.model_api_key is None:
        from moira.ai.fake import FakeLLM

        llm = FakeLLM()
    else:
        from moira.ai.client import MetaLLM
        from moira.ai.usage import Budget
        from moira.db.connection import open_db
        from moira.db.migrate import migrate

        system = open_db(settings.data_dir / "system.db")
        migrate(system, "system")
        llm = MetaLLM(settings, Budget(system, settings, SystemClock()), SystemClock())
        settings.model_main = settings.model_contrib  # synthetic data: contributor mode only
    built = asyncio.run(
        build_template(
            args.out, settings=settings, llm=llm, embedder=embedder, now=SystemClock().now()
        )
    )
    sys.stdout.write(f"built {built.path} with {len(built.keys)} anchors\n")
    from moira.sandbox.welcome import write_welcome_sky

    write_welcome_sky(built.path, ROOT / "web" / "public" / "welcome-sky.json")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
