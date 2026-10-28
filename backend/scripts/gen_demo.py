"""Generate data/demo/nuggets.jsonl (blueprint §11.3). Synthetic data only.

    uv run python scripts/gen_demo.py --offline          # curated lists, deterministic, free
    uv run python scripts/gen_demo.py                    # DEMO_GEN per month (contributor model)

Rows: {key?, text, source, day_offset, hour, minute, image_text?, research?}. ``day_offset`` is
days before "now" when the template is built. The anchors of data/demo/anchors.jsonl are merged
in. A human reviews the output before it is committed.
"""

import argparse
import asyncio
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "demo" / "nuggets.jsonl"
ANCHORS = ROOT / "data" / "demo" / "anchors.jsonl"

POOLS: dict[str, list[tuple[str, str]]] = {
    "tech": [
        ("typed", "pc fix: update chipset drivers before the gpu driver"),
        ("typed", "valorant stutter fixed after turning off the overlay in discord"),
        ("youtube", "https://www.youtube.com/watch?v=tUnE5pcB0aT clean windows install guide"),
        ("typed", "ram at 3200 now, checked in task manager"),
        ("voice", "remember the case fan curve, set it to 60 percent at 70 degrees"),
        ("typed", "monitor set to 165hz in display settings, it was stuck at 60"),
        ("web", "https://blog.example.com/undervolting-gpu-basics"),
        ("typed", "router: change wifi channel to 36 if the room gets laggy"),
        ("typed", "ssd health 96% in crystaldisk, fine"),
        ("github", "https://github.com/demo-tools/fan-control"),
        ("typed", "bios update done, version F12, keep the usb stick"),
        ("typed", "obs settings: nvenc, 6000 kbps, 1080p60 for clips"),
        ("youtube", "https://www.youtube.com/watch?v=pcB1ldG8kT2 budget pc build 2026"),
        ("typed", "laptop charger is the 65W one, not the 45W"),
        ("typed", "turn off hardware acceleration in chrome if videos flicker"),
        ("voice", "the headset mic was muted in windows sound settings, not discord"),
    ],
    "ai": [
        ("instagram", "https://www.instagram.com/reel/AiSk3tchUi1/ ai that turns sketches into ui"),
        (
            "instagram",
            "https://www.instagram.com/reel/BgRem0ver22/ background remover that actually works",
        ),
        (
            "youtube",
            "https://www.youtube.com/watch?v=aiAg3ntz101 building an ai agent in an afternoon",
        ),
        ("github", "https://github.com/demo-labs/prompt-kit"),
        ("typed", "tried an ai music tool, good for lofi loops"),
        (
            "instagram",
            "https://www.instagram.com/reel/VoiCeCl0ne3/ voice cloning demo, a bit scary",
        ),
        ("web", "https://news.example.com/small-models-on-laptops"),
        ("typed", "idea: use ai to tag my old photos by place"),
        ("youtube", "https://www.youtube.com/watch?v=rAgExpl41n2 rag explained in 10 minutes"),
        ("github", "https://github.com/demo-labs/tiny-embeddings"),
        ("instagram", "https://www.instagram.com/reel/SubT1tleAi4/ auto subtitles in 40 languages"),
        ("typed", "ai upscaler made the old game textures look sharp"),
        ("web", "https://research.example.com/why-static-embeddings-are-fast"),
        ("instagram", "https://www.instagram.com/reel/ThumbN41l5x/ ai thumbnail generator"),
        ("typed", "note to self: ai coding tools are great for tests, check every diff"),
    ],
    "design": [
        ("typed", "portfolio: hero should say what I build in one line"),
        ("web", "https://design.example.com/case-study-structure"),
        ("typed", "font pair idea: jost for headings, system ui for text"),
        ("github", "https://github.com/demo-design/portfolio-starter"),
        ("typed", "dark palette #0B0B0C #151516 #F4F4F5 looks calm"),
        ("instagram", "https://www.instagram.com/reel/GrIdLay0ut6/ grid layouts for portfolios"),
        ("typed", "case study 1: the bus app redesign, show before and after"),
        ("typed", "ask josh for feedback on the about page"),
        ("web", "https://type.example.com/variable-fonts-guide"),
        ("typed", "motion: cards should grow out of where you tapped"),
        ("youtube", "https://www.youtube.com/watch?v=dsgnCr1t1q7 portfolio critique session"),
        ("typed", "accent only on data, chrome stays neutral"),
        ("typed", "contrast check: muted text 9.5:1 on the dark ground"),
    ],
    "music": [
        ("typed", "song stuck in my head: lofi beat with rain sounds"),
        ("youtube", "https://www.youtube.com/watch?v=l0f1Rain88q rainy lofi mix for studying"),
        ("typed", "playlist idea: focus mornings, no lyrics"),
        ("voice", "that nepali indie band from the festival, the drummer was amazing"),
        ("typed", "learn the intro riff on guitar this weekend"),
        ("web", "https://music.example.com/jazz-standards-for-beginners"),
        ("typed", "album to listen: anything by the trio guy recommended"),
        ("typed", "headphones sound better with the eq preset flat"),
        ("voice", "the cafe in jhamsikhel had a great playlist, ask them"),
    ],
    "places": [
        ("typed", "cafe with good wifi in jhamsikhel, upstairs seats"),
        ("typed", "trek idea: shivapuri on a clear morning"),
        ("web", "https://travel.example.com/pokhara-weekend"),
        ("typed", "momo place near the college, the jhol one"),
        ("typed", "bookshop in thamel with old design books"),
        ("voice", "the rooftop place in patan had the best sunset view"),
        ("typed", "coworking space with day passes near baneshwor"),
        ("typed", "nagarkot sunrise, leave at 4am"),
    ],
    "todo": [
        ("typed", "todo: renew library card"),
        ("typed", "buy a new mouse pad"),
        ("typed", "submit assignment for networks before friday"),
        ("typed", "call the bank about the student account"),
        ("typed", "todo: back up the portfolio repo"),
        ("typed", "book a dentist appointment"),
        ("typed", "reply to the internship email"),
        ("typed", "pay the internet bill"),
        ("typed", "todo: print the visa form"),
        ("typed", "return guy's controller"),
        ("typed", "clean the pc dust filters"),
        ("typed", "todo: update the cv with the hackathon"),
        ("typed", "send alex the photos from the trek"),
        ("typed", "buy oat milk"),
    ],
    "ideas": [
        ("typed", "idea: an app that turns notes into a night sky"),
        ("typed", "idea: a bot that reminds me to drink water while gaming"),
        ("voice", "what if the timeline was the colour key for the stars"),
        ("typed", "idea: blog post about tuning a budget pc"),
        ("typed", "idea: portfolio case study as a scrolling story"),
        ("typed", "idea: a study timer that blocks game launchers"),
        ("typed", "idea: map of quiet cafes with good wifi"),
        ("typed", "idea: a tiny tool to export discord chats to markdown"),
        ("voice", "maybe a youtube series about building small ai tools"),
        ("typed", "idea: shared playlist for the friend group"),
    ],
    "learning": [
        ("youtube", "https://www.youtube.com/watch?v=sqlL1t3ftS9 sqlite full text search tutorial"),
        ("web", "https://docs.example.com/learn-typescript-in-a-week"),
        ("typed", "course: distributed systems lectures, start week 3"),
        ("typed", "read the book Clean Architecture"),
        ("typed", "read the book The Design of Everyday Things"),
        ("web", "https://cs.example.com/how-transformers-work"),
        ("typed", "practice leetcode graphs this week"),
        ("youtube", "https://www.youtube.com/watch?v=canvasR3nd2 canvas 2d performance tips"),
        ("typed", "read the book Refactoring, chapter 6"),
    ],
    "watch": [
        ("typed", "watch: the new sci-fi series everyone talks about"),
        ("youtube", "https://www.youtube.com/watch?v=d0cuM3nt4ry documentary about game design"),
        ("typed", "movie night: something with a twist ending"),
        ("typed", "watch the hackathon kickoff recording"),
        ("typed", "anime recommendation from alex: the one about chess"),
    ],
    "notes": [
        ("typed", "gym at 6 works better than 8"),
        ("typed", "electricity cut schedule changed, evenings now"),
        ("voice", "remember the plumber number is on the fridge"),
        ("typed", "bus fare went up to 30"),
        ("typed", "sleep before midnight this week, exams"),
        ("typed", "the printer needs the blue cable, not the white one"),
        ("typed", "mom's birthday dinner on saturday"),
        ("typed", "college wifi password changes every month, ask the office"),
        ("typed", "laptop stickers: keep the moira one"),
        ("typed", "water filter replaced today"),
    ],
}
PEOPLE = [
    ("typed", "Alex's birthday is 14 March"),
    ("typed", "Guy got a job at a studio in Lalitpur"),
    ("typed", "Alex is moving to Pokhara next month"),
    ("typed", "Guy's phone is +977 9801234567"),
    ("typed", "Alex's email is alex.k@example.com"),
    ("typed", "my coffee order is a flat white"),
    ("typed", "switched to oat cortado these days"),
]
SCREENSHOTS = [
    "Order confirmed · Mechanical keyboard · Arrives Thursday",
    "Exam timetable · Networks: 12 Nov 10:00 · Databases: 15 Nov 14:00",
    "Wi-Fi: CafeUpstairs · Ask staff for the code",
    "Flight Kathmandu → Pokhara · Seat 4A · 7:30 am",
]


def offline(seed: int = 7) -> list[dict[str, object]]:
    rng = random.Random(seed)  # noqa: S311  # synthetic data
    items: list[dict[str, object]] = []
    for pool in POOLS.values():
        for source, text in pool:
            items.append({"text": text, "source": source})
    for source, text in PEOPLE:
        items.append({"text": text, "source": source})
    for text in SCREENSHOTS:
        items.append({"text": "", "source": "screenshot", "image_text": text})
    # Repeat with small variations to reach ~300, denser in recent months.
    variants = []
    for item in items:
        if item["source"] in ("typed", "voice") and rng.random() < 0.6:
            variants.append({**item, "text": f"{item['text']} again"})
    items += variants
    for item in items:
        recent = rng.random() < 0.55
        item["day_offset"] = rng.randint(1, 120) if recent else rng.randint(121, 720)
        item["hour"] = rng.choice([8, 9, 11, 13, 15, 17, 19, 20, 21, 22, 23])
        item["minute"] = rng.randint(0, 59)
    return items


async def online(months: int) -> list[dict[str, object]]:
    """DEMO_GEN per month with the contributor model (synthetic data only)."""
    from moira.ai import prompts
    from moira.ai.client import InputPart, MetaLLM
    from moira.ai.schemas import DemoGenOutput
    from moira.ai.usage import Budget
    from moira.app_services import startup_services

    services = startup_services(
        __import__("moira.config", fromlist=["load_settings"]).load_settings()
    )
    llm = MetaLLM(
        services.settings,
        Budget(services.system, services.settings, services.clock),
        services.clock,
    )
    persona = (ROOT / "data" / "demo" / "persona.md").read_text(encoding="utf-8")
    items: list[dict[str, object]] = []
    for m in range(months):
        prompt = prompts.load("demo_gen")
        out = await llm.structured(
            prompt=prompt,
            inputs=[
                InputPart(
                    text=f"<persona>{persona}</persona>\n"
                    f"<month>{m} months ago</month>\n<count>12</count>"
                )
            ],
            schema=DemoGenOutput,
            effort="low",
            max_output_tokens=4000,
            timeout_s=120,
            user_id=None,
            kind="demo_gen",
            model=services.settings.model_contrib,
        )
        for it in out.items:
            items.append(
                {
                    "text": it.text,
                    "source": it.source,
                    "day_offset": m * 30 + max(0, 30 - it.day),
                    "hour": it.hour,
                    "minute": it.minute,
                }
            )
    return items


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--months", type=int, default=24)
    args = ap.parse_args(argv)
    items = offline() if args.offline else asyncio.run(online(args.months))
    anchors = [
        json.loads(line) for line in ANCHORS.read_text(encoding="utf-8").splitlines() if line
    ]
    rows = sorted(
        anchors + items, key=lambda r: (-int(r["day_offset"]), int(r["hour"]), int(r["minute"]))
    )  # type: ignore[call-overload]
    OUT.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"wrote {len(rows)} rows to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
