# Moira

For anyone who wants to know what Moira is, try it, or run it.

> Text it like a friend. Ask it like a friend.

Moira is a memory you text. Send anything to the Moira Telegram bot or type it into the Moira web app (text, a link, a screenshot, a voice note) and forget about it. Moira reads it, researches bare links on the web, files everything as text, keeps facts up to date without losing history, and finds anything again from a vague memory ("two weeks ago, an Instagram link, something about AI"). Your memory is drawn as a night sky you can zoom into, and every answer flies you to the exact star.

Named after the Moirai of Greek myth, who spin and measure the thread of every life.

**Status:** under construction during the Meta Global AI Developer Hackathon (Indie track, theme "Build for Your World"). The live demo link, sky GIF and benchmark numbers will appear here as each milestone ships.

## Try it

- Live demo: _coming with v0.5.0_
- Try the sample memory: _coming with v0.9.0_
- Judges: _instructions coming with v0.9.0_

## Features

- **Capture never asks.** Saving is instant; the bot reacts with 👌 and nothing else.
- **Bare links researched at save time** and kept as text, even if the post disappears later.
- **Facts that change keep their history.** The **Now** line updates; the old fact moves to **Earlier**; every change can be undone.
- **Search the way people remember:** time, source, people and topic together, even when the date you remember is slightly off.
- **A stable night sky** where each star is one memory and never moves once placed.

## How Meta AI is used

Muse Spark 1.3 reads images and screen recordings, files every save with structured output, researches links with web search (verified in code), plans queries and answers with citations. Muse Voice Transcribe turns voice notes into text, biased with names from your own memory. Details: [blueprint §9](docs/blueprint/BLUEPRINT.md).

## Architecture

One Python process (FastAPI + aiogram bot + job worker) with one SQLite file per memory, on a free 1 GB server; a Preact web app draws the sky on a canvas. See [ARCHITECTURE.md](ARCHITECTURE.md).

## How it was built

Moira is built during the event with **Claude Code**, one task at a time from the [blueprint](docs/blueprint/BLUEPRINT.md) (Appendix M). Claude Code writes most of the code. The developer makes the product and design decisions, wrote the blueprint, reviews every pull request, tests on real phones, and prepares the sample data, the evaluation and the video. Every AI-assisted commit carries an `Assisted-by: Claude Code` trailer, and [DEVLOG.md](DEVLOG.md) records each work session.

## Quick start

See [docs/howto/LOCAL_DEV.md](docs/howto/LOCAL_DEV.md). In short: `make setup`, then `make dev` (runs with a fake model unless `MODEL_API_KEY` is set).

## Cost

Hosting is $0 on a free 1 GB server. The AI costs about $3 a month for everyday use and up to $10 at very heavy use.

## Documentation

- [Blueprint](docs/blueprint/BLUEPRINT.md) · [Decisions](docs/adr/) · [Open questions](docs/OPEN_QUESTIONS.md)
- [Security](SECURITY.md) · [Privacy](PRIVACY.md) · [Changelog](CHANGELOG.md) · [Devlog](DEVLOG.md)

## Licence

[MIT](LICENSE)
