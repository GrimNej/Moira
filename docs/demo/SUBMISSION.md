# Submission text

For the submission form: the text submitted on the platform (blueprint §15.2). Fields in
[brackets] are filled on submission day.

## Submission text

**Name and tagline:** Moira — "Text it like a friend. Ask it like a friend."

**Track and theme:** Indie developer · Build for Your World.

**Problem:** People save things everywhere and find almost nothing again. Notes apps need names
and folders, search needs the exact words, and a link saved without a note is effectively lost.
What people actually remember is vague: roughly when, where it came from, and what it was about.

**What it does:** A memory you text: send it anything and it reads, researches and files it as
text, keeps your facts up to date with history, and finds anything again from a vague memory.
Your memory is drawn as a night sky, and every answer flies you to the exact star.

Three moments:

1. "insta link about AI, ~2 weeks ago" finds a reel saved with no note, researched at save time.
2. "my favorite fruit is now banana" updates the fact and keeps apple as history, with Undo.
3. The sky grows week by week on the timeline; nothing ever moves once placed.

**How it uses Meta AI:** see the table in the README (vision, structured output, web search,
video understanding and reasoning with Muse Spark 1.3; Muse Voice Transcribe for voice notes).
The save pipeline is a multi-step agent: read → research → verify in code → file → update facts.

**Technical depth:** hybrid retrieval (full text, trigrams, exact strings, vectors) with
telescoping-aware time priors; doc2query-style questions stored at save time; web research
verified by post ID; a prompt-injection firewall for facts (only the user's own words can
change one); a text-only design in one SQLite file per memory on a free 1 GB server; budget
caps with a degraded mode; a benchmark with ablations.

**Impact evidence:** [testers], [found-it rate], [R@5 with the real model], about $3 a month in
AI cost for everyday use.

**Links:** live app [url] · GitHub <https://github.com/GrimNej/Moira> · demo video [url] ·
X post [url].

**Contributors:** the developer (solo). **How it was built:** Claude Code wrote most of the code
from the blueprint in `docs/blueprint/`; the developer made the product and design decisions,
reviewed the pull requests, tested on real phones, wrote the sample data, ran the evaluation and
made the video.

**How to judge it:** Open [url] → Try the sample memory → tap any suggestion → Show in sky. For
the Telegram bot: open t.me/[bot]?start=[judge-code] (your own private copy). Everything shown is
sample data.

**Honesty notes:** the sample data is synthetic; costs are stated plainly; English only; nothing
behind a login is read; iPhone sharing goes through Telegram.

**Submitted:** [date and time, NPT]
