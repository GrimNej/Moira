# Changelog

All notable changes to this project are documented here.
Format: Keep a Changelog 1.1.0 · Versioning: SemVer.

## [Unreleased]

## [0.6.0] - 2026-10-28

### Added

- Try the sample memory: a private copy for 24 hours, with times shifted so "two weeks ago" is
  always two weeks ago. Judges get their own copy from an invite link.
- Nightly upkeep: importance, tidy (merges near-duplicate constellations and fixes unclear
  names, at most 5 a night, each undoable), index repair and a secret audit.
- A daily digest for the owner with saves, questions, spend, research, dead jobs and backups.
- Nightly encrypted backups off the server, a restore script and a timed restore drill.
- Export everything as JSONL, Markdown and a SQLite file; weekly export to Telegram; forget
  everything with a 24-hour grace period.
- Short screen recordings are read into text (speech, on-screen text, creator).

### Security

- ffmpeg reads only local files, with the input format pinned to the checked file type.
- Saved links become clickable only for http and https.
- The threat model is checked row by row in SECURITY.md.

## [0.5.0] - 2026-10-28

### Added

- The web app: your memory as a night sky that you can zoom, scrub through time and play;
  the card for one memory; Ask with streamed, cited answers; Recent; settings.
- Save from the web: text, screenshots and voice notes, with a comet that lands as a star and
  an Undo toast. Saves made offline wait and send when you are back online.
- Install the web app; on Android, share from any app straight into Moira.

### Fixed

- A new star's Undo toast no longer goes missing when filing finishes before the save reply.

## [0.4.0] - 2026-10-28

### Added

- Ask in plain words, in Telegram or on the web: instant results, then a cited answer, with
  lists, counts and follow-ups.
- Voice notes are transcribed; screenshots are read; the evaluation harness and sample memory.

## [0.3.0] - 2026-10-28

### Added

- Every save is read, researched when it is a bare link, filed into constellations, and facts
  update with their history.

## [0.2.0] - 2026-10-28

### Added

- Save anything to the Telegram bot: text, links, photos, albums, voice notes, short videos,
  forwards, locations and contacts. The bot reacts with 👌.
- Passwords, card numbers, one-time codes and keys are hidden before anything is stored.
- Sign in to the web app with a one-time link from /web, or automatically inside Telegram.
- Commands: /start with invites, /web, /forget with Undo, /undo, /timezone, /help.

## [0.1.0] - 2026-10-28

### Added

- Repository layout, blueprint, design prototype and agent instructions.
