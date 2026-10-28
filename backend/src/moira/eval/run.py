"""Evaluation harness (§12.4): ``python -m moira.eval run --config all --cache .eval-cache``.

Builds the eval memory from data/demo once (cached), runs data/eval/queries.jsonl with a
FixedClock at each query's asked time, prints the metrics table and appends a dated row per
config to docs/eval/RESULTS.md. Uses FakeLLM unless --real (contributor model, synthetic data).
"""

import argparse
import asyncio
import json
import random
import subprocess
import sys
import time as _time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from moira.ai import prompts
from moira.config import load_settings
from moira.demo import ROOT, TZ, build_template
from moira.eval.ablations import CONFIGS, retrieve
from moira.eval.cache import CachedLLM
from moira.eval.metrics import Metrics, QueryResult, compute

QUERIES = ROOT / "data" / "eval" / "queries.jsonl"
RESULTS = ROOT / "docs" / "eval" / "RESULTS.md"
NOW = datetime(2026, 10, 26, 21, 0, tzinfo=ZoneInfo(TZ))


def resolve_expected(conn, q: dict, keys: dict[str, str]) -> list[int]:  # type: ignore[no-untyped-def,type-arg]
    ids: list[int] = []
    for k in q.get("expected_keys", []):
        if k in keys:
            row = conn.execute("SELECT id FROM nuggets WHERE public_id = ?", (keys[k],)).fetchone()
            if row:
                ids.append(row[0])
    for text in q.get("expected_text", []):
        rows = conn.execute(
            "SELECT id FROM nuggets WHERE (user_text LIKE ? OR content_text LIKE ?)"
            " AND deleted_at IS NULL",
            (f"%{text}%", f"%{text}%"),
        ).fetchall()
        ids += [r[0] for r in rows]
    return list(dict.fromkeys(ids))


async def evaluate(configs: list[str], cache: Path, real: bool) -> dict[str, Metrics]:
    from moira.ai.fake import FakeLLM
    from moira.app_services import wire
    from moira.capture.service import CaptureService
    from moira.clock import FixedClock
    from moira.db.connection import open_db
    from moira.db.migrate import migrate
    from moira.db.repos import users
    from moira.embed.model import load_embedder
    from moira.jobs.queue import Queue
    from moira.memory.create import get_meta
    from moira.memory.registry import Memories
    from moira.search.ask import AskService
    from moira.search.parse import parse
    from moira.services import Services

    settings = load_settings()
    embedder = load_embedder(
        settings.embed_model,
        settings.embed_dim,
        settings.embed_quantize,
        fake=settings.app_env == "test" or not real,
    )
    inner = FakeLLM()
    if real:
        from moira.ai.client import MetaLLM
        from moira.ai.usage import Budget
        from moira.clock import SystemClock

        system = open_db(settings.data_dir / "system.db")
        migrate(system, "system")
        settings.model_main = settings.model_contrib  # synthetic data only
        inner = MetaLLM(settings, Budget(system, settings, SystemClock()), SystemClock())  # type: ignore[assignment]
    llm = CachedLLM(inner, cache / "llm")
    mem_path = cache / f"eval-{'real' if real else 'fake'}.db"
    if not mem_path.exists():
        await build_template(mem_path, settings=settings, llm=llm, embedder=embedder, now=NOW)

    work = cache / "work"
    work.mkdir(parents=True, exist_ok=True)
    clock = FixedClock(NOW)
    system = open_db(work / "system.db")
    migrate(system, "system")
    memories = Memories(
        cache, clock, embed_model=settings.embed_model, embed_dim=settings.embed_dim
    )
    user = users.by_public_id(system, "u_evaluserxxxx") or users.create(
        system,
        public_id="u_evaluserxxxx",
        kind="judge",
        memory_path=mem_path.name,
        tz=TZ,
        now=clock.now_ms(),
    )
    capture = CaptureService(
        system=system,
        memories=memories,
        queue=Queue(system, clock, random.Random(1)),  # noqa: S311  # jitter only
        clock=clock,
        embedder=embedder,
    )
    services = wire(
        Services(settings, clock, system, memories, capture.queue, embedder, capture), llm
    )
    conn = memories.open(mem_path.name)
    keys = json.loads(get_meta(conn, "sample_keys") or "{}")
    queries = [
        json.loads(line) for line in QUERIES.read_text(encoding="utf-8").splitlines() if line
    ]
    out: dict[str, Metrics] = {}
    for name in configs:
        cfg = CONFIGS[name]
        results = []
        for q in queries:
            clock.set(NOW + timedelta(days=q.get("asked_offset_days", 0)))
            expected = resolve_expected(conn, q, keys)
            started = _time.monotonic()
            p = parse(q["question"], clock.now(), TZ)
            ranked = retrieve(conn, p, cfg, TZ, embedder)
            r = QueryResult(q["id"], q["category"], expected, ranked)
            if cfg.answer:
                res = await AskService(services).ask(user, q["question"])
                cited = [c["id"] for c in res.citations]
                if cited:
                    row = conn.execute(
                        "SELECT id FROM nuggets WHERE public_id = ?", (cited[0],)
                    ).fetchone()
                    r.top_cite = row[0] if row else None
                existing = {x[0] for x in conn.execute("SELECT public_id FROM nuggets")}
                r.hallucinated = sum(1 for c in cited if c not in existing)
                r.not_found = res.confidence == "not_found"
            r.seconds = _time.monotonic() - started
            results.append(r)
        out[name] = compute(results, cfg.answer)
    return out


def commit_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],  # noqa: S607
            capture_output=True,
            text=True,
            check=True,
            cwd=ROOT,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def fmt(v: float | None) -> str:
    return "—" if v is None else f"{v:.2f}"


def table(results: dict[str, Metrics], model: str) -> list[str]:
    from moira.clock import SystemClock

    date = SystemClock().now().astimezone(ZoneInfo(TZ)).strftime("%Y-%m-%d %H:%M")
    versions = "/".join(prompts.load(n).version for n in ("enrich", "answer", "plan"))
    rows = []
    for name, m in results.items():
        rows.append(
            f"| {date} | {commit_sha()} | {name} | {versions} | {model} | {m.n} | {fmt(m.r1)} |"
            f" {fmt(m.r5)} | {fmt(m.mrr10)} | {fmt(m.top_cite)} | {fmt(m.nf_precision)} |"
            f" {m.hallucinated} | — | — | {m.p50_s:.2f} | {m.usd_per_q:.4f} |"
            f" {'FakeLLM: pipeline check, not model quality' if model == 'fake' else ''} |"
        )
    return rows


def chart(results: dict[str, Metrics], path: Path) -> None:
    """A dependency-free SVG bar chart of Recall@5 by config."""
    w, h, bar = 480, 220, 40
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        'viewBox="0 0 480 220" font-family="system-ui" font-size="12">',
        '<rect width="480" height="220" fill="#0b0b0c"/>',
    ]
    for i, (name, m) in enumerate(results.items()):
        x = 30 + i * 55
        bh = int(160 * m.r5)
        parts.append(f'<rect x="{x}" y="{180 - bh}" width="{bar}" height="{bh}" fill="#b0c8ff"/>')
        parts.append(
            f'<text x="{x + 20}" y="198" fill="#b4b4b8" text-anchor="middle">{name}</text>'
        )
        parts.append(
            f'<text x="{x + 20}" y="{174 - bh}" fill="#f4f4f5" text-anchor="middle">'
            f"{m.r5:.2f}</text>"
        )
    parts.append('<text x="10" y="16" fill="#f4f4f5">Recall@5 by config</text></svg>')
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="moira.eval")
    sub = ap.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run")
    run.add_argument("--config", default="all")
    run.add_argument("--cache", type=Path, default=Path(".eval-cache"))
    run.add_argument("--real", action="store_true", help="contributor model (spends credits)")
    run.add_argument("--no-write", action="store_true")
    args = ap.parse_args(argv)
    configs = list(CONFIGS) if args.config == "all" else [c.strip() for c in args.config.split(",")]
    results = asyncio.run(evaluate(configs, args.cache, args.real))
    model = "muse-spark-1.3-contributor" if args.real else "fake"
    rows = table(results, model)
    sys.stdout.write("config  n   R@1   R@5   MRR10  cite  nf-prec  halluc\n")
    for name, m in results.items():
        sys.stdout.write(
            f"{name:6}  {m.n:<3} {m.r1:.2f}  {m.r5:.2f}  {m.mrr10:.2f}   "
            f"{fmt(m.top_cite):5} {fmt(m.nf_precision):7}  {m.hallucinated}\n"
        )
    if not args.no_write:
        with RESULTS.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(rows) + "\n")
        if len(results) > 1:
            chart(results, ROOT / "docs" / "media" / "eval_recall_by_config.svg")
    return 0
